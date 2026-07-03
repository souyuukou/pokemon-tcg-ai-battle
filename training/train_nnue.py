"""Train the compact sparse policy/value network from replay JSON files.

Usage: python training/train_nnue.py --data data/20260625 --out sample_submission/model.nnue
"""
from __future__ import annotations
import argparse, hashlib, json, random, struct
from pathlib import Path
import numpy as np

FEATURES, HIDDEN, MAGIC, VERSION = 4096, 128, b"PKNNUE1\0", 2


def hfeature(text: str) -> int:
    h = 2166136261
    for b in text.encode():
        h = ((h ^ b) * 16777619) & 0xffffffff
    return h % FEATURES


def features(obs: dict) -> list[int]:
    cur = obs.get("current") or {}; out = []
    yi = cur.get("yourIndex", 0)
    for pi, p in enumerate(cur.get("players", [])):
        side = "us" if pi == yi else "them"
        out += [hfeature(f"{side}:prize:{len(p.get('prize', []))}"), hfeature(f"{side}:deck:{p.get('deckCount',0)//4}")]
        for zone in ("active", "bench", "discard", "hand"):
            for card in p.get(zone) or []:
                if card:
                    out.append(hfeature(f"{side}:{zone}:{card.get('id',0)}"))
                    if "hp" in card: out.append(hfeature(f"{side}:{zone}:hp:{card['hp']//20}"))
    out += [hfeature(f"turn:{cur.get('turn',0)//2}"), hfeature(f"first:{cur.get('firstPlayer',-1)==yi}")]
    return sorted(set(out))


def action_features(obs: dict, option: dict) -> list[int]:
    select = obs["select"]
    values = [f"context:{select.get('context', -1)}", f"type:{option.get('type', -1)}"]
    for key in ("cardId", "attackId", "area", "index", "playerIndex",
                "inPlayArea", "inPlayIndex", "number", "count",
                "specialConditionType"):
        if option.get(key) is not None:
            values.append(f"{key}:{option[key]}")
    if option.get("type") is not None and option.get("cardId") is not None:
        values.append(f"type_card:{option['type']}:{option['cardId']}")
    area_names = {2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}
    area = option.get("area", 2 if option.get("type") in (7, 8, 9) else None)
    player = option.get("playerIndex", (obs.get("current") or {}).get("yourIndex", 0))
    index = option.get("index")
    try:
        card = obs["current"]["players"][player][area_names[area]][index]
        if card:
            values += [f"resolvedCard:{card['id']}", f"type_resolved:{option.get('type',-1)}:{card['id']}"]
    except (KeyError, IndexError, TypeError):
        pass
    return sorted(set(hfeature("action:" + value) for value in values))


def examples(files: list[Path]):
    random.shuffle(files)
    for path in files:
        try: replay = json.loads(path.read_text(encoding="utf-8"))
        except Exception: continue
        rewards = replay.get("rewards", [0, 0])
        for pair in replay.get("steps", []):
            for pi, step in enumerate(pair):
                if not step or not step.get("observation", {}).get("select"): continue
                obs = step["observation"]; action = step.get("action") or []
                opts = obs["select"].get("option", [])
                if not opts: continue
                selected = int(action[0] if action else 0)
                yield (features(obs), [action_features(obs, option) for option in opts],
                       float(rewards[pi]), min(selected, len(opts) - 1))


def export(path: Path, emb, bias, value, value_bias, action_emb):
    scale_e = max(float(np.max(np.abs(emb))), float(np.max(np.abs(action_emb)))) / 127
    scale_e = max(scale_e, 1e-8)
    scale_v = max(float(np.max(np.abs(value))) / 127, 1e-8)
    qe = np.clip(np.rint(emb / scale_e), -127, 127).astype(np.int8)
    qv = np.clip(np.rint(value / scale_v), -127, 127).astype(np.int8)
    qa = np.clip(np.rint(action_emb / scale_e), -127, 127).astype(np.int8)
    payload = qe.tobytes() + np.asarray(bias, np.float32).tobytes() + qv.tobytes() + struct.pack("<f", float(value_bias)) + qa.tobytes()
    checksum64 = 14695981039346656037
    for byte in payload:
        checksum64 = ((checksum64 ^ byte) * 1099511628211) & 0xffffffffffffffff
    checksum = struct.pack("<Q", checksum64) + bytes(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<8sIIIIff32s", MAGIC, VERSION, FEATURES, HIDDEN, len(payload), scale_e, scale_v, checksum) + payload)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--data",type=Path,required=True);ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--epochs",type=int,default=2);ap.add_argument("--limit",type=int,default=0);a=ap.parse_args()
    try: import torch; from torch import nn
    except ImportError as e: raise SystemExit("PyTorch is required for offline training") from e
    random.seed(7); np.random.seed(7); torch.manual_seed(7)
    files=list(a.data.rglob("*replay.json")); random.Random(7).shuffle(files)
    if a.limit: files=files[:a.limit]
    split=max(1,int(len(files)*.9)); train_files=files[:split]; valid_files=files[split:]
    class Net(nn.Module):
        def __init__(self):
            super().__init__(); self.emb=nn.EmbeddingBag(FEATURES,HIDDEN,mode="sum");self.value=nn.Linear(HIDDEN,1);self.action_emb=nn.EmbeddingBag(FEATURES,HIDDEN,mode="sum")
        def state(self, ids, offsets):
            return torch.clamp(self.emb(ids,offsets),0,127)
        def forward(self, ids, offsets, action_ids, action_offsets):
            state=self.state(ids,offsets); actions=self.action_emb(action_ids,action_offsets)
            return torch.tanh(self.value(state)).squeeze(1),(actions*state).sum(1)/(HIDDEN**.5)
    net=Net();opt=torch.optim.AdamW(net.parameters(),lr=2e-3)
    for epoch in range(a.epochs):
        count=0;loss_sum=0.
        for fs,action_fs,val,selected in examples(train_files):
            ids=torch.tensor(fs,dtype=torch.long);off=torch.tensor([0]); target=torch.tensor([val],dtype=torch.float32)
            flat=[item for group in action_fs for item in group]; starts=[]; at=0
            for group in action_fs: starts.append(at); at+=len(group)
            vv,logits=net(ids,off,torch.tensor(flat,dtype=torch.long),torch.tensor(starts,dtype=torch.long)); target_action=torch.tensor([selected])
            loss=(vv-target).square().mean()+.05*nn.functional.cross_entropy(logits.unsqueeze(0),target_action)
            opt.zero_grad();loss.backward();opt.step();count+=1;loss_sum+=loss.item()
        print(f"epoch={epoch+1} examples={count} loss={loss_sum/max(count,1):.5f}")
    if valid_files:
        net.eval(); total=correct=0; value_error=0.
        with torch.no_grad():
            for fs,action_fs,val,selected in examples(valid_files):
                flat=[item for group in action_fs for item in group]; starts=[]; at=0
                for group in action_fs: starts.append(at); at+=len(group)
                vv,logits=net(torch.tensor(fs,dtype=torch.long),torch.tensor([0]),torch.tensor(flat,dtype=torch.long),torch.tensor(starts,dtype=torch.long))
                value_error+=abs(vv.item()-val);correct+=int(logits.argmax().item()==selected);total+=1
        print(f"validation examples={total} value_mae={value_error/max(total,1):.5f} policy_acc={correct/max(total,1):.5f}")
    export(a.out,net.emb.weight.detach().numpy(),np.zeros(HIDDEN,np.float32),net.value.weight.detach().numpy()[0],net.value.bias.item(),net.action_emb.weight.detach().numpy())
if __name__=="__main__":main()
