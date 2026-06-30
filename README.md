# LRA Reading Categorizer

Human-in-the-loop categorization tools for the Learning Real Analysis reading
library.

This repository starts with an approved modern mathematics subject taxonomy.
The taxonomy is intentionally separate from any PDF-copy workflow so the GUI can
use a stable target tree for manual categorization.

## Current Structure

- `taxonomy/subjects.yaml` is the structured source of truth for labels and
  stable folder slugs.
- `subjects/` mirrors the approved taxonomy as a reference scaffold.
- `readings/` mirrors the approved taxonomy as the eventual managed reading
  library destination.

The next step is to design a Python GUI for manual PDF categorization.

## Manual Categorization GUI

Seed or refresh the recoverable SQLite queue from `lra-source-profiles`:

```powershell
python scripts\categorizer.py import --source-profiles F:\repos\lra-source-profiles
```

Launch the GUI:

```powershell
python scripts\categorizer.py gui
```

The GUI shows one deduped canonical PDF at a time, opens the PDF in Chrome, and
lets you edit title, ISBN, first author, main category, subcategory, and notes.
Changing the main category updates the subcategory dropdown. `Save` copies the
PDF into `readings/<main>/<sub>/` and marks the record saved. `Skip` marks the
record skipped without copying. Both actions are persisted in SQLite.

Useful command-line checks:

```powershell
python scripts\categorizer.py status
python scripts\categorizer.py export --out review\categorization-progress.csv
```

## Safety Intent

- Do not delete source PDFs.
- Do not move source PDFs without explicit approval.
- Keep classifier output as hints, not as final placement.
- Treat local BibTeX sections as context, not authority.
