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

## Independent PR review follow-up

An independent inline reviewer (separate from the resolver; nested delegation was
unavailable) reproduced a synthetic config safety bypass: CR before a comment
made the old checker and `bash -n` pass, while isolated Bash sourcing created a
temporary marker. This was not a real config or provider action. The restricted
parser now rejects non-LF controls/separators before comments, preserves Bash's
double-quoted backslash semantics and rejects unsupported unquoted shell syntax.
New tests compare accepted synthetic literal values against both available Bash
versions; no user config is sourced. Checker PASS still describes only checked
bytes, not later edits/replacement or the runtime's arbitrary sourcing behavior.

The review also requires launcher provenance **before** executing help, and actual
configured-token authenticated exact-zone/owning-account reads rather than browser
visibility as resource-access proof. Six new offline regression/contract methods
bring this suite to 28 methods; the unchanged 156 shell cases remain separate.
Three additional adversarial prompts are supplied, but were not run as measured
with-skill/baseline evaluations. These review fixes do not replace skill-standard
certification: a fresh `asm eval --json` on skill 1.0.3 again measured 87, license
0 (all other categories at least 8; body 1,495 words). Thus skill-standard Gate 2
remains BLOCKER. Quick validation passed with no warnings. Targeted regression
tests against the original checker were red, and against the repaired checker
green. License selection and behavioral/human-output certification remain
outstanding; no independent agent adherence benchmark is claimed.

## Maintainer evaluation procedure

Use `evals/evals.json` for offline scenario evaluations. Never use real credentials,
provider writes or mail sends for evaluation. Run the config/contract tests with
`python3 tests/skill_setup_test.py` from the source repository; they do not prove
live setup or agent adherence. Keep behavioral evals and human-understanding review
separate from these tests. Grade actual outputs for main result findability,
fact/assumption separation, claim-to-evidence traceability and clear next decision.
Ask human reviewers the same four questions; absent feedback means understanding
is unconfirmed, not passed. Provider steps need user interaction and cannot be
safely delegated away from that consent/evidence boundary. All references and
scripts travel with this directory;
no other skill or future documentation issue is required.

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

The original `evals.json` had three happy paths, four adversarial edges and one
negative trigger; PR review added three adversarial prompts (eleven total).
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

## Skill 1.1.0 — context discovery (issue #11)

The skill now opens with read-only discovery (`references/discovery.md`) instead of
asking about setup mode, OS/terminal/browser access or installation status. Mode
is inferred from request cues; an unnamed failed gate is found by rerunning
read-only checks in gate order. Undetectable facts, including browser access, stay
`unknown` and are asked only at the gate that needs them. Discovery never executes
a found cmail, reads `.env`, calls providers or changes state.

Three prompts were added (ids 12–14: bare setup request, vague breakage, advice-only
without a shell tool; fourteen total); they are scenario cases, not measured
behavioral runs. Two
offline contract methods were added: discovery precedes mode/gates and the removed
opening questions stay absent, and the `.agents/skills/cmail-setup` discovery copy
stays byte-identical to `skills/cmail-setup`. Both were red before the change.

To keep `SKILL.md` under the context-efficiency budget, the probe table and context
block live in `references/discovery.md`, the maintainer procedure moved into this
file, and two edge-case bullets duplicated by the safety contract and advice-only
mode were folded in. `asm eval --json` measured 87 before and after (license 0,
all other categories at least 8; body 1,499 words). Skill-standard Gate 2 remains a
BLOCKER on license only; human understanding of the new opening remains unconfirmed.

Review follow-up: probes now describe the agent's shell, so a conflicting user fact
or a resume cue with no install marks the target machine `unknown` until Gate 1.
Discovery adds an exact path-override `printenv`, `ENV_FILE` metadata, zsh
`whence -w`, a guarded checkout `.env` probe and a ban on environment dumps; Gate 2
reuses the discovered OS/config path. The contract test now regex-scans `SKILL.md`
and every reference for the removed questions and checks the `.claude` symlink.
Re-measured: 30 offline methods pass; `asm eval --json` 87 (structure 9, PII 8,
license 0, all others 10); body 1,499 words.

Second review: a found launcher's install-time `default_config` is invisible to
discovery, so Config stays `unknown` until Gate 1 provenance allows reading that
line as metadata; any agent-seen `ENV_FILE` is confirmed at Gate 2. The override
probe is a labelled per-variable loop (multi-name `printenv` is unportable), Gate 1
names zsh `whence -w`, and the contract test bans three more question forms.
Re-measured: 30 offline methods pass; `asm eval --json` 87 (structure 9, PII 8,
license 0, all others 10); body 1,499 words.
