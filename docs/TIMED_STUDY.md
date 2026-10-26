# Measuring minutes saved

The number a clinic founder acts on is prep time per member. We do not estimate it. We measure it.

## Protocol

1. Pick 10 members from the synthetic cohort (`data/demo`). Mix easy and hard ones.
2. Recruit 3 to 5 people. Clinicians are best. Health science students are an honest second choice. State which you used.
3. Each person preps **5 members by hand** and **5 with Copilot**. Swap which half each person gets, so no member is only ever done one way.
4. "Prep" means: read every PDF, note what changed since the last draw, write a draft plan and a member message.
5. Time from opening the first PDF to a finished draft. Record it in `docs/timed_study.csv`.
6. A second person blind-checks each output for missed critical values and wrong numbers. Speed with errors does not count.

## Report

```
python scripts/timed_study.py docs/timed_study.csv
```

It prints median minutes per member for each arm, the difference, the number of people and members, and the error count per arm. Publish all of it, including a small sample size.

## CSV format

```
participant,role,member_id,arm,minutes,errors
p1,clinician,M1003,manual,14.5,0
p1,clinician,M1004,copilot,4.0,0
```
