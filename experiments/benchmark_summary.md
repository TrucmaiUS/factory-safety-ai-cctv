# Benchmark Summary

## Purpose

This file tracks future model experiments for the Factory Safety AI project.
Phase 2 does not train models and does not invent benchmark numbers. All metrics
remain `TBD` until experiments are run on a validated YOLO dataset.

The project is an AI Safety Risk Scoring & Decision System. Detection models are
only the Perception Layer. Model outputs will later be converted into risk
signals for:

`Perception -> Context Analysis -> Risk Scoring -> Decision -> Action`

## Candidate Models

| Model ID | Base model | Role | Status |
|---|---|---|---|
| `yolo8s_ppe` | YOLOv8s | Stable baseline | TBD |
| `yolo11s_ppe` | YOLO11s | Primary candidate | TBD |
| `public_ppe_baseline` | TBD | External baseline if license and label map are clear | TBD |

## Metrics To Measure Later

| Model ID | mAP50 | mAP50-95 | Precision | Recall | FPS | False alarm rate | Risk event detection consistency | Decision |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `yolo8s_ppe` | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| `yolo11s_ppe` | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| `public_ppe_baseline` | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## Notes

- FPS must be measured for both one-camera and three-camera modes.
- False alarm rate should be evaluated after Rule Engine and Confidence Fusion
  are connected, not from raw model predictions alone.
- Risk event detection consistency means whether the system produces stable
  event decisions and avoids duplicate/spam alerts for the same tracked person.
- No benchmark value in this file should be filled without a reproducible run.
