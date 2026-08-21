# Fall Injury Scale Research and System Mapping

Generated: 2026-05-20

## Conclusion

The existing `I0` to `I5` scale can be kept, but its meaning should be tightened. Industry and healthcare quality reporting usually grade fall injury outcomes as:

`none / minor / moderate / major / death`

The system therefore maps:

| System Level | Meaning | External Basis |
| --- | --- | --- |
| `I0` | No fall or no apparent injury | none/no injury |
| `I1` | Suspected fall or near-fall observation | system-specific pre-injury triage level |
| `I2` | Minor injury risk | minor injury |
| `I3` | Moderate injury risk | moderate injury |
| `I4` | Major injury or emergency-assessment risk | major injury |
| `I5` | Life-threatening or death | death/life-threatening outcome |

`I1` is intentionally not a clinical injury outcome. It exists because the camera system has a real operational stage where the model has suspicious evidence but the event is not yet confirmed.

## Important Design Rule

The model must not claim a clinical diagnosis. It may produce an injury-risk triage level and response priority. Death or actual injury confirmation must come from human review or trusted external records.

## How This Changes the System

The old meaning was mostly engineering-driven:

- `I1`: minor fall, recovered and observed
- `I2`: delayed/slightly abnormal recovery
- `I3`: moderate injury risk
- `I4`: severe injury risk
- `I5`: emergency risk

The updated meaning is outcome-aligned:

- `I1` is downgraded to suspected/near-fall observation.
- `I2` becomes the first confirmed-fall injury-risk level.
- `I4` is aligned with major injury indicators such as inability to rise, need for assistance, suspected fracture/dislocation/head injury, abnormal consciousness, heavy bleeding, chest pain, or abnormal breathing.
- `I5` is reserved for life-threatening conditions or externally/human-confirmed death.

## Files Updated

- `configs/fall_detection/fall_injury_scale.yaml`
- `configs/fall_detection/room_camera_injury_rules.yaml`
- `fall_detection_model_bundle/configs/injury_rules.yaml`

## Sources

- AHRQ PSNet describes fall-related injury classification as `none`, `minor`, `moderate`, `major`, and `death`, citing NDNQI fall-related injury classification.
- AHRQ On-Time Falls Prevention reporting guidance separates falls with minor injury from falls with major injury, and lists major examples such as hip/other fractures, joint dislocations, closed head injuries with altered consciousness, and subdural hematomas.
- CMS long-term care quality-measure material focuses on falls with major injury and uses diagnosis evidence for serious injuries such as traumatic fractures.

Reference links:

- https://psnet.ahrq.gov/web-mm/falling-through-crack-bedrails
- https://www.ahrq.gov/patient-safety/settings/long-term-care/resource/ontime/fallspx/reportguide.html
- https://www.cms.gov/files/document/fmi-technicalspecificationsreport-nh.pdf
