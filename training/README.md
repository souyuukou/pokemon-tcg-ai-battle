# NNUE training

`python training/train_nnue.py --data data/20260625 --out sample_submission/model.nnue`

Replay files are split by whole match, so positions from one match are never
split independently. Model format v2 contains sparse state embeddings and
dynamic action embeddings keyed by context, card, attack, area, and target.
The exported file also contains dimensions, quantization scales, and a verified
64-bit payload checksum. Training is offline only; the submitted agent has no
PyTorch dependency.
