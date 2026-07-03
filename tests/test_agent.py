import pathlib, struct, sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "sample_submission"))
from fallback import choose
from pvs_wire import VERSION as WIRE_VERSION
from pvs_wire import _pack_option
sys.path.insert(0, str(ROOT))
from training.train_nnue import action_features
from training.train_nnue import hfeature


def obs(lo, hi, types):
    return {"select":{"minCount":lo,"maxCount":hi,"option":[{"type":t} for t in types]}}


def test_fallback_legality():
    for lo, hi in [(0,0),(0,1),(1,1),(2,3)]:
        o=obs(lo,hi,[14,7,13,10]); a=choose(o)
        assert lo <= len(a) <= hi
        assert len(a)==len(set(a)) and all(0 <= x < 4 for x in a)


def test_action_priority():
    assert choose(obs(1,1,[14,7,13])) == [2]


def test_deck_is_valid():
    cards=[int(x) for x in (ROOT/"sample_submission"/"deck.csv").read_text().split()]
    assert len(cards)==60


def test_action_features_distinguish_cards_and_targets():
    observation={"select":{"context":0},"current":{"yourIndex":0,"players":[{"hand":[{"id":10},{"id":20}]},{}]}}
    first=action_features(observation,{"type":7,"index":0})
    second=action_features(observation,{"type":7,"index":1})
    assert first != second


def test_model_v2_checksum():
    data=(ROOT/"sample_submission"/"model.nnue").read_bytes()
    magic,version,nf,nh,size,_,_,checksum,_=struct.unpack("<8sIIIIffQ24s",data[:64])
    value=14695981039346656037
    for byte in data[64:]: value=((value^byte)*1099511628211)&0xffffffffffffffff
    assert (magic,version,nf,nh,size)==(b"PKNNUE1\0",2,4096,256,len(data)-64)
    assert value==checksum


def test_feature_schema_hashes_match_native_contract():
    expected={
        "first:True":4041,
        "first:False":3492,
        "us:active:hp:3":2424,
        "them:bench:hp:12":72,
        "action:type_card:7:123":3031,
        "action:type_resolved:8:722":269,
    }
    assert {text:hfeature(text) for text in expected}==expected


def test_wire_preserves_attached_card_identity():
    packed = _pack_option({
        "type": 5, "toolIndex": 2, "energyIndex": 3, "serial": 123456,
    })
    assert WIRE_VERSION == 2
    assert struct.unpack("<hhi", packed[-8:]) == (2, 3, 123456)
