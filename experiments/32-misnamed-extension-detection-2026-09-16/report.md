# Experiment 32: Does Magika spot the real file type when the name lies?

**ID:** 32-misnamed-extension-detection-2026-09-16
**Date:** 16 September 2026
**Status:** PASS, all 5 checks passed
**Feeds proof into:** ADR-068, the decision record that says why we use Magika

## The question

When you add a file, the system must work out its type: PDF, program code, Markdown, or plain text. A wrong guess sends the file to the wrong reader, and the stored text comes out broken.

The system uses a tool called Magika to name the type. Magika reads the file's contents, not its name. Most systems guess from the file ending, like `.pdf` or `.py`. This experiment asked one thing: does Magika still get the type right when the file name lies?

## What I did

1. Took 19 real PDFs from experiment 31. Eight are damaged files that show no readable words; the other eleven are healthy.
2. Took 11 text files from this project: Python code, Markdown notes, plain notes.
3. Copied every file. The originals were never touched.
4. Renamed the PDF copies to `.py`, `.md`, or `.txt`.
5. Renamed the text copies to `.pdf`.
6. Asked Magika to name each copy's type.

Nothing was added to any document store. No search ran. This was a naming test only.

## The result

| Set | Files | Outcome |
| --- | ----- | ------- |
| PDFs with honest names | 19 | All 19 named correctly |
| Text files with honest names | 11 | All 11 named correctly |
| PDFs renamed to look like code or notes | 19 | All 19 still named PDF, which is correct |
| Text files renamed to look like PDFs | 11 | All 11 still named by their real type, which is correct |

The raw output shows exit code 1 for the two renamed sets. That is not a crash. It is the mismatch flag: the name-based guess and Magika's answer differ. Here that is the wanted result. It proves Magika read the contents and ignored the lying name.

Each check took under one second. No crash, no timeout, no fallback to name guessing.

## Why this matters

A name-based system would send a PDF named `notes.py` to the code reader. The wrong reader produces broken stored text. Magika stops that before it starts, because the file goes to the right reader based on what is inside it.

The damaged PDFs matter most. The part of a PDF that holds readable words is broken in them, but the outer container is a normal PDF. Magika named them correctly anyway. So even damaged files reach the PDF readers.

## Honest limits

1. This tested naming only. No files were stored and no search ran.
2. Very short files can fool the detector. We knew this already; ADR-068 records it.
3. The files came from this project's earlier work. Other kinds, like images or zip files, were not tested.

## Where the proof lives

- `protocol.md`: the plan and expected answers, written before the run
- `build_swaps.py`: makes the renamed copies
- `run_detection.py`: runs the naming checks
- `summarise_eval.py`: judges pass or fail
- `analysis.py`: prints the result tables
- `output/`: raw results for every file
