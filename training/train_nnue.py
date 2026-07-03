"""Train the compact sparse policy/value network from replay JSON files.

Usage: python training/train_nnue.py --data data/20260625 --out sample_submission/model.nnue
"""
from __future__ import annotations
import argparse, json, random, struct, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

sys_path = Path(__file__).resolve().parents[1] / "sample_submission"
if str(sys_path) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(sys_path))
from action_codec import validate_action
from observation_sanitize import sanitize_observation

FEATURES, HIDDEN, MAGIC, VERSION = 4096, 256, b"PKNNUE1\0", 2


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
        for zone in ("active", "bench", "discard"):
            for card in p.get(zone) or []:
                if card:
                    out.append(hfeature(f"{side}:{zone}:{card.get('id',0)}"))
                    if "hp" in card: out.append(hfeature(f"{side}:{zone}:hp:{card['hp']//20}"))
        if pi == yi:
            for card in p.get("hand") or []:
                if card:
                    out.append(hfeature(f"{side}:hand:{card.get('id',0)}"))
        else:
            out.append(hfeature(f"{side}:hand:{int(p.get('handCount',0))//4}"))
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


def examples_from_path(path: Path):
    try:
        replay = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    rewards = replay.get("rewards", [0, 0])
    for pair in replay.get("steps", []):
        for pi, step in enumerate(pair):
            if not step or not step.get("observation", {}).get("select"):
                continue
            obs = sanitize_observation(step["observation"])
            action = [int(index) for index in (step.get("action") or [])]
            opts = obs["select"].get("option", [])
            if not opts:
                continue
            reward = rewards[pi] if pi < len(rewards) else 0
            if reward is None:
                continue
            select = obs["select"]
            if not validate_action(action, select):
                continue
            for pick in action:
                out.append((
                    np.asarray(features(obs), dtype=np.int64),
                    [np.asarray(action_features(obs, option), dtype=np.int64) for option in opts],
                    float(reward),
                    min(pick, len(opts) - 1),
                ))
    return out


def load_examples(files: list[Path], workers: int, cache: Path | None):
    if cache and cache.is_file():
        import torch
        print(f"loading cache {cache}", flush=True)
        t0 = time.time()
        data = torch.load(cache, weights_only=False)
        print(f"cache_loaded examples={len(data)} elapsed={time.time()-t0:.1f}s", flush=True)
        return data
    if workers <= 1:
        data = []
        for i, path in enumerate(files, 1):
            data.extend(examples_from_path(path))
            if i % 5000 == 0:
                print(f"extract progress={i}/{len(files)} examples={len(data)}", flush=True)
    else:
        data = []
        done = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(examples_from_path, path): path for path in files}
            for future in as_completed(futures):
                data.extend(future.result())
                done += 1
                if done % 5000 == 0:
                    print(f"extract progress={done}/{len(files)} examples={len(data)}", flush=True)
    if cache:
        import torch
        cache.parent.mkdir(parents=True, exist_ok=True)
        torch.save(data, cache)
        print(f"cache_saved {cache} examples={len(data)}", flush=True)
    return data


def collate_batch(batch):
    state_parts, state_offsets = [], []
    action_parts, action_offsets, action_owner = [], [], []
    values, selected, action_ranges = [], [], []
    action_row = 0
    for i, (state_ids, action_groups, value, pick) in enumerate(batch):
        state_offsets.append(len(state_parts))
        state_parts.extend(state_ids.tolist())
        row_start = action_row
        for action_ids in action_groups:
            action_offsets.append(len(action_parts))
            action_parts.extend(action_ids.tolist())
            action_owner.append(i)
            action_row += 1
        action_ranges.append((row_start, action_row))
        values.append(value)
        selected.append(pick)
    return (
        np.asarray(state_parts, dtype=np.int64),
        np.asarray(state_offsets, dtype=np.int64),
        np.asarray(action_parts, dtype=np.int64),
        np.asarray(action_offsets, dtype=np.int64),
        np.asarray(action_owner, dtype=np.int64),
        np.asarray(values, dtype=np.float32),
        np.asarray(selected, dtype=np.int64),
        action_ranges,
    )


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


def train_epoch(net, data, device, opt, batch_size, amp, scaler, policy_weight):
    import torch
    from torch import nn

    net.train()
    order = torch.randperm(len(data)).tolist()
    count = 0
    loss_sum = 0.0
    t0 = time.time()
    for start in range(0, len(order), batch_size):
        idx = order[start:start + batch_size]
        batch = [data[i] for i in idx]
        (
            state_parts, state_offsets, action_parts, action_offsets,
            action_owner, values, selected, action_ranges,
        ) = collate_batch(batch)
        state_ids = torch.as_tensor(state_parts, device=device)
        state_off = torch.as_tensor(state_offsets, device=device)
        action_ids = torch.as_tensor(action_parts, device=device)
        action_off = torch.as_tensor(action_offsets, device=device)
        owner = torch.as_tensor(action_owner, device=device)
        target = torch.as_tensor(values, device=device)
        picks = torch.as_tensor(selected, device=device)
        opt.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, enabled=amp):
            hidden = net.state(state_ids, state_off)
            values_pred = torch.tanh(net.value(hidden)).squeeze(1)
            actions = net.action_emb(action_ids, action_off)
            logits = (actions * hidden[owner]).sum(1) / (HIDDEN ** 0.5)
            value_loss = (values_pred - target).square().mean()
            policy_loss = torch.zeros((), device=device)
            for i, (lo, hi) in enumerate(action_ranges):
                policy_loss = policy_loss + nn.functional.cross_entropy(logits[lo:hi].unsqueeze(0), picks[i:i + 1])
            policy_loss = policy_loss / len(batch)
            loss = value_loss + policy_weight * policy_loss
        if amp:
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
        else:
            loss.backward()
            opt.step()
        count += len(batch)
        loss_sum += float(loss.item()) * len(batch)
        if count % 50000 < batch_size:
            rate = count / max(time.time() - t0, 1e-6)
            print(f"progress={count} loss={loss_sum/count:.5f} ex_per_sec={rate:.0f}", flush=True)
    return count, loss_sum


def evaluate(net, data, device, batch_size):
    import torch

    net.eval()
    total = correct = 0
    value_error = 0.0
    with torch.no_grad():
        for start in range(0, len(data), batch_size):
            batch = data[start:start + batch_size]
            (
                state_parts, state_offsets, action_parts, action_offsets,
                action_owner, values, selected, action_ranges,
            ) = collate_batch(batch)
            state_ids = torch.as_tensor(state_parts, device=device)
            state_off = torch.as_tensor(state_offsets, device=device)
            action_ids = torch.as_tensor(action_parts, device=device)
            action_off = torch.as_tensor(action_offsets, device=device)
            owner = torch.as_tensor(action_owner, device=device)
            hidden = net.state(state_ids, state_off)
            values_pred = torch.tanh(net.value(hidden)).squeeze(1)
            actions = net.action_emb(action_ids, action_off)
            logits = (actions * hidden[owner]).sum(1) / (HIDDEN ** 0.5)
            for i, (lo, hi) in enumerate(action_ranges):
                pick = int(selected[i])
                value_error += abs(float(values_pred[i].item()) - float(values[i]))
                correct += int(int(logits[lo:hi].argmax().item()) == pick)
                total += 1
    return total, value_error, correct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--no-amp", action="store_true")
    a = ap.parse_args()
    try:
        import torch
        from torch import nn
        from torch.amp import GradScaler
    except ImportError as e:
        raise SystemExit("PyTorch is required for offline training") from e
    random.seed(7)
    np.random.seed(7)
    torch.manual_seed(7)
    files = [p for p in a.data.rglob("*.json") if p.is_file() and "-" not in p.stem
             and (p.stem.isdigit() or p.name.endswith("replay.json"))]
    random.Random(7).shuffle(files)
    print(f"replay_files={len(files)}", flush=True)
    if a.limit:
        files = files[:a.limit]
    split = max(1, int(len(files) * .9))
    train_files, valid_files = files[:split], files[split:]
    cache = a.cache or (a.data / "_nnue_cache.pt")

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.EmbeddingBag(FEATURES, HIDDEN, mode="sum")
            self.value = nn.Linear(HIDDEN, 1)
            self.action_emb = nn.EmbeddingBag(FEATURES, HIDDEN, mode="sum")

        def state(self, ids, offsets):
            return torch.clamp(self.emb(ids, offsets), 0, 127)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = device.type == "cuda" and not a.no_amp
    print(f"device={device} batch_size={a.batch_size} workers={a.workers} amp={amp}", flush=True)

    train_data = load_examples(train_files, a.workers, cache)
    valid_data = load_examples(valid_files, a.workers, None) if valid_files else []
    print(f"train_examples={len(train_data)} valid_examples={len(valid_data)}", flush=True)

    net = Net().to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3)
    scaler = GradScaler(device.type, enabled=amp)
    for epoch in range(a.epochs):
        count, loss_sum = train_epoch(net, train_data, device, opt, a.batch_size, amp, scaler, 0.05)
        print(f"epoch={epoch + 1} examples={count} loss={loss_sum / max(count, 1):.5f}", flush=True)
    if valid_data:
        total, value_error, correct = evaluate(net, valid_data, device, a.batch_size)
        print(
            f"validation examples={total} value_mae={value_error / max(total, 1):.5f} "
            f"policy_acc={correct / max(total, 1):.5f}",
            flush=True,
        )
    export(
        a.out,
        net.emb.weight.detach().cpu().numpy(),
        np.zeros(HIDDEN, np.float32),
        net.value.weight.detach().cpu().numpy()[0],
        net.value.bias.item(),
        net.action_emb.weight.detach().cpu().numpy(),
    )


if __name__ == "__main__":
    main()
