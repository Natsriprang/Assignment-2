# Reference library

Clause-level reference texts for the drafting steps. Each `.json` file is one source document, already
cleaned and split into entries. The original Word, PDF and DOC files are not part of the repository.

| File | What it is | Rights |
|---|---|---|
| `th_gov_construction_contract.json` | Thai government standard construction contract form, English version translated with GPT (not reviewed by a lawyer) | Official form; Thai Copyright Act s.7. Verify |
| `ca_long_version.json` | Longer version of the app's own template | Not public. Author's own document; confirm before sharing |
| `epc_subcontract_agreement.json` | Rooftop PV subcontract (anonymised) | Not public. Author's own document; confirm before sharing |

## Entry fields

`id`, `article`, `title`, `category`, `text`, `our_clause` (the key in `core/clause_data.py` it corresponds to, or
`null`), `gap` (the topic is missing or thin in the app's current library), `quality_notes` (drafting slips and
differences worth knowing), and `similarity_to_ours` (0 to 1, word overlap with the mapped clause, where mapped).

## Edits made when preparing the files

Each file lists its `scrubs` (specific names, amounts, dates and addresses replaced by placeholders) and `edits`.
Everything else keeps the source wording, including its mistakes, which are recorded in `quality_notes`.

Check: `python -m tests.test_reference_library`
