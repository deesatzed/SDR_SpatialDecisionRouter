# Synthetic clinician-review GUI

This local Flask interface supports review of preconfigured **synthetic** corpus conversions. It is not a clinical decision interface, does not contact a model or network, does not read or write patient data, and cannot modify trigger parameters, clinician rulings, the case library, or the queue fixture.

Run it from the repository root:

```bash
python -m homehealth.review_gui.app
```

It binds only to `127.0.0.1:5000`. Local review state and the append-only event record are stored in `~/.homehealth-review/review.sqlite3`.

Each case shows the preconfigured expected trigger result beside a fresh result from `aether_review.trigger_adapter`. A reviewer can approve a conversion only after all five checks are selected and the recomputed result matches. They can also retain a local structured edit, route a conversion for clinician review, or exclude it. These actions create local audit records; they do not promote a result into the frozen corpus.

The included `fixtures/queue.json` is intentionally a one-case synthetic demonstration. Expanding it needs separately approved, structured synthetic inputs and clinician-ruling references before they can be reviewed in the UI.
