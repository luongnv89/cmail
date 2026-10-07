# Evaluation record

## Result: implementation checked; skill certification incomplete

The skill is not claimed publish-ready. `asm eval` measured 87/100, but the
license category is 0, below the required minimum 8. This repository has no
LICENSE; selecting redistribution rights requires the maintainer. No license
was invented to improve an evaluator score.

## Checks actually run

- `python3 tests/skill_setup_test.py`: 22 offline unittest methods passed. They
  exercise private literal config, missing fields, invalid formats, quoting,
  duplicate/runtime-control keys, command/expansion rejection, no execution,
  value-free diagnostics, symlink/FIFO/directory/mode rejection and size/encoding
  boundaries. Structural tests check reference paths, installer/input/tool
  guidance, nine gate contracts, fail-closed wording and evaluation-case floor.
- Existing seven shell suites: 156 offline cases passed (121 runtime plus 35
  installer). Existing tests were not edited or weakened.
- Bash syntax checks and `git diff --check`: passed.
- Skill-creator `quick_validate.py`: valid with no warnings.
- `asm eval --fix --dry-run`: no deterministic fixes needed.
- `asm eval --json`: baseline 77 → final 87. Final categories: structure 9,
  description 10, prompt engineering 10, context efficiency 10, safety 10,
  testability 10, license 0, naming 10, PII 8, script lint 10. The PII finding
  includes the existing public author identity and synthetic example addresses;
  no private user data was collected. Body measured 1,431 words, under both caps.
- Five hand mutations in a throwaway source copy made focused tests fail, then
  restored green: remove documented installer command (AC1); remove jq version
  check (AC2); omit required Cloudflare token (AC3); remove a gate verification
  clause (AC4); remove a repair/recheck clause (AC5). These are config/structure
  sensitivities, not proof an agent obeys the instructions at runtime.

## Instruction and predictability audit

Frontmatter name/directory, quoted values, semver/author, negative triggers and
portable reference paths were checked. No other skill is invoked; dependency
lease metadata is therefore not applicable. README notice/template sections are
present. Bundled script failure messages identify the input/check and local repair
without printing values.

The five human-review instruction checks: controlled actions/conditions, result/
evidence/uncertainty/decision output contract, short text format, four understanding
criteria and missing-feedback handling are present. Interactive report requirement
is not applicable: one setup needs a small gate ledger, not candidate filtering.
Human understanding itself remains **unconfirmed**: no user feedback was solicited
in this autonomous implementation.

Predictability walk: intentional explicit-request invocation; new/resume/advice
branches; demanding per-gate evidence; focused reference disclosure; named gate
states; pruning/reconciliation against current installer; publish-ready check.
The last item fails because license quality floor is unmet. Provider steps are
not delegated because local secrets, browser actions and consent require the user.

## Scenario walkthroughs, not behavioral runs

`evals.json` has three happy paths, four adversarial edges and one negative trigger.
An author logic/edge-case walkthrough checked these prescribed responses:

| Case | Expected gate behavior |
|---|---|
| Missing macOS install | Guide reviewed `bash install.sh`, recheck launcher help/PATH, no provider work. |
| Installed config + OAuth | Select installed config, ask missing non-secret inputs, browser/local secrets, verify config before provider access. |
| One alias outbound bounced | Gate 9 remains partial; one alias cannot prove another; recheck both directions after repair. |
| Active token / zone 403 | Block zone gate; fix resource scope then repeat lookup, no duplicate zone or purchase. |
| DRY_RUN with existing DNSSEC/MX | No global safety claim; migration/DS plan and specific consent before DNS writes. |
| Credential pasted into chat | Do not echo; rotate/revoke, replace locally, no full doctor capture. |
| Uncertain nameserver write / Pending | Inspect registrar post-state, wait/recheck Active, no dependent routing writes. |
| Announcement copy | Do not trigger setup or ask for provider secrets. |

`eval-viewer/generate_review.py` generated a static review page from these
explicitly labeled author walkthroughs. Local artifact:
`/tmp/cmail-setup-workspace/review.html` (not a distributable skill dependency).
No grades, behavioral baseline, timings, pass-rate delta or human feedback were
fabricated. The delegation tool was disabled; no fresh independent adversarial
subagent or with-skill/without-skill agent evaluation was available. Two advisor
risk reviews informed the plan and conservative parser boundaries, but are not
represented as independent behavioral runs.

## Remaining checks / decision

Author static instruction audit and deterministic tests passed; independent
instruction/behavioral review remains unmeasured. Skill-standard certification
**Gate 2 BLOCKER** (distinct from setup gate 2): license score 0 despite overall 87.
Independent behavioral discovery/logic/edge runs and human understanding remain
unmeasured. After a maintainer licensing
decision, rerun both skill-standard gates and with-skill/baseline evaluations.
This PR does not select a license or authorize publication, provider actions or
user setup; no publication is performed.

No user installation, provider access, domain purchase, DNS write, browser alias
confirmation, SMTP authentication or actual send/receive delivery was executed.
