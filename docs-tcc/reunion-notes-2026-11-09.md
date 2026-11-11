# Notes for the meeting with Prof. Ronaldo — 2026-11-09

Local support file (not versioned). Reference PDF: the interim report generated on 2026-11-09 from the `revisao-ronaldo-v23` branch.

## What changed in this preview

- **Ch. 4, §4.6 (interface):**
  - "overwrite table" became "input CSV files";
  - the edit mode was explained: while it is active, the typed text applies; on leaving it, that text is discarded and the interface's command returns;
  - the paragraph "The alternative…" was removed;
  - Figure 15 now says it is a simulation;
  - Figure 17 highlights the "Check DBMSs" button.
- **Ch. 4, §4.5.1:** the old numbers (batch writing ~9× faster; block reading with a 12.5× lower peak) justify why the naive strategy and materialization were abandoned. Ch. 5 no longer uses them.
- **Ch. 5 rewritten:**
  - final version only;
  - five research questions, in order;
  - volumes in powers of 2, from 1,024 to 262,144 rows;
  - scalability analysis with a log-log plot and a fitted exponent;
  - the figures that repeated tables were removed.
- **Conclusion:** "Final Remarks" and "Future Work" became a single chapter, with its own closing paragraph.

## Answers to the questions

- **Why do time and memory come from separate runs?** To measure peak memory, Python has to record every allocation (the `tracemalloc` module). This makes the import about 3.3× slower, and unevenly so: inference, which allocates heavily, becomes 6.2× slower, while the Cassandra write, which spends its time waiting for the database, only becomes 2.1× slower. Times from a run with memory measurement are therefore not valid. That is why each configuration runs twice: once to time it and once to measure memory.
- **Why were the workloads different?** The old measurements were made with a version that still had the naive write and materialization. Those options no longer exist in the code, and the MongoDB `orders` collection was added later. Ch. 5 now measures only the final version, and the old numbers were summarized in §4.5.1 as a justification.
- **Seed 42:** it is the number that initializes the pseudorandom generator. The same seed always generates the same files, byte for byte, which makes the campaigns comparable. The value 42 is arbitrary; what matters is that it stays fixed.
- **Host ("hospedeiro"):** it is the experiment machine (Intel Core i5-8265U with 8 logical processors, 8 GB of RAM, SSD, Windows 11). In the new text, the term no longer appears.
- **Default 8 MB block:** it was the **smallest** of the three blocks tested (8, 64 and 256 MB), not the largest. In the current version, the default is 128 MB, and the tool will soon choose the block on its own.
- **"Finished" → "Data import finished":** Figure 15 is a **simulation** (`--dry-run`), whose message is "Finished dry-run — nothing was written". "Data import finished" would be false, because nothing was imported. A real import already says "Finished import — N partition(s) written".
- **"Isolated":** it meant "not investigated". The text was corrected.
- **English interface:** will be done. The new figures will be added after the translation.

## What comes next

- **Automatic choice of block and batch:** an exploratory campaign measures time and memory for several sizes. The chosen block becomes the smallest one that already gives the best time, capped at a fraction of the machine's free memory. Both controls are removed from the interface.
- **English interface**, with the figures redone.
- **Final campaign** on the version with the automatic choice, and tool version 3.2.0.

## Questions for him

1. Does the scalability analysis (log-log plot, exponent and verdict) answer what he asked for?
2. Is the summarized justification in §4.5.1 enough to explain why the naive strategy and materialization were abandoned?
3. Does he prefer to keep the per-DBMS tables at the largest volume, or to also show an intermediate volume?
