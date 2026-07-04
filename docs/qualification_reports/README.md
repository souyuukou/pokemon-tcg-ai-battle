# Qualification Reports

Machine-generated qualification evidence is written to:

```text
artifacts/qualification/<commit_sha>/
```

Run on a **clean** working tree:

```bash
python tools/qualify_runtime.py --soak-games 50
```

Outputs:

- `qualification_status.json`
- `runtime_v1_qualification_report.md`
- `pytest_output.txt`
- `soak_authoritative.json`
- `soak_no_authoritative.json`
- `artifact_e2e_result.json`

`artifacts/` is gitignored. To record a qualification snapshot in git, copy the report summary into a separate commit and set `tested_commit` explicitly.
