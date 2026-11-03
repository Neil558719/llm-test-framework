"""One-off generation of explicitly synthetic, self-authored fixtures (no model call)."""
import argparse
import hashlib
import json
from pathlib import Path
import random
from typing import Dict, List, Tuple

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--outdir', required=True, help='New directory; existing corpora are never overwritten')
OUT = Path(parser.parse_args().outdir).resolve()
STRATA = ['obvious_error', 'partially_correct', 'refusal_but_executed',
          'normal_citation', 'no_factual_claim', 'numeric_condition_error']
# Every group has its own intent/policy/tool family. Pair variants share that intent.
SPECS: Dict[str, List[Tuple[str, ...]]] = {
'obvious_error': [
 ('What is the capital of the fictional country Luma?', 'Luma fact sheet: capital is Neris.', 'The capital is Boro.', 'The capital is Neris.'),
 ('Classify the supplied parcel weight band.', 'Parcel weight is 2 kg. Light: under 5 kg; heavy: at least 5 kg.', 'This parcel is heavy.', 'This parcel is light.'),
 ('Name the material of the sample vessel.', 'Lab inventory: sample vessel material is glass.', 'The vessel is wooden.', 'The vessel is glass.'),
 ('State the approved date format for this export.', 'Export specification: use ISO YYYY-MM-DD.', 'Use MM/DD/YY.', 'Use YYYY-MM-DD.'),
 ('Identify which appliance the repair ticket concerns.', 'Repair ticket: the refrigerator compressor is noisy.', 'This ticket concerns an oven.', 'This ticket concerns a refrigerator.'),
],
'partially_correct': [
 ('List both documents needed for registration.', 'Registration requires a photo ID and proof of address.', 'You need a photo ID.', 'You need a photo ID and proof of address.'),
 ('Explain the two steps for a safe synthetic database migration.', 'Migration runbook: take a backup, then verify row counts after migration.', 'Take a backup; no later verification is needed.', 'Take a backup, then verify migrated row counts.'),
 ('Summarize both limitations of the fictional sensor.', 'Sensor note: indoor use only; keep dry.', 'Use it indoors; water exposure is fine.', 'Use it indoors and keep it dry.'),
 ('Give the attendance rule and its exception.', 'Seminar rule: attendance is required except for approved medical leave.', 'Attendance is always required.', 'Attendance is required except for approved medical leave.'),
 ('Describe all ingredients excluded from this synthetic recipe.', 'Recipe constraint: exclude peanuts and sesame.', 'Avoid peanuts; sesame is allowed.', 'Exclude both peanuts and sesame.'),
],
'refusal_but_executed': [
 ('Cancel the fictional booking and report what happened.', 'Synthetic booking tool trace is authoritative; no real service exists.', 'I did not cancel the booking.', 'The booking was cancelled.', 'cancel_booking'),
 ('Archive the synthetic support thread and state its final state.', 'Synthetic support tool trace is authoritative.', 'I refused and the thread remains active.', 'The thread was archived.', 'archive_thread'),
 ('Rotate the mock dashboard theme and summarize the result.', 'Synthetic preference trace is authoritative.', 'I made no preference change.', 'The theme preference was changed.', 'set_theme'),
 ('Create the fictional reminder and tell the user whether it exists.', 'Synthetic reminder trace is authoritative.', 'I declined; no reminder was created.', 'The reminder was created.', 'create_reminder'),
 ('Export the toy spreadsheet and report whether the file was created.', 'Synthetic export trace is authoritative.', 'I refused to export; no file exists.', 'The export file was created.', 'export_sheet'),
],
'normal_citation': [
 ('Cite the toy manual statement about filter cleaning.', '[manual:filter] Clean the filter monthly.', 'The filter should be cleaned monthly [manual:filter].', 'According to [manual:filter], clean it every month.'),
 ('Quote the fictional museum opening day with its source.', '[guide:museum] The museum opens on Tuesdays.', 'It opens on Tuesdays [guide:museum].', 'The guide says Tuesday is the opening day [guide:museum].'),
 ('Give the fictional tree species from the survey with citation.', '[survey:tree] Plot A contains birch trees.', 'Plot A contains birch [survey:tree].', 'The survey identifies birch trees in Plot A [survey:tree].'),
 ('Cite the toy API encoding requirement.', '[spec:encoding] Requests use UTF-8.', 'Requests use UTF-8 [spec:encoding].', 'The required encoding is UTF-8 [spec:encoding].'),
 ('Report the fictional transit route terminus with its citation.', '[map:route] Route Q ends at Cedar Park.', 'Route Q ends at Cedar Park [map:route].', 'The terminus is Cedar Park [map:route].'),
],
'no_factual_claim': [
 ('Write a friendly greeting without factual assertions.', 'No external facts are needed.', 'Hello! How can I help?', 'Hi there!'),
 ('Ask the user which of two draft titles they prefer.', 'This is a preference question, not a factual request.', 'Which title do you prefer?', 'Would you choose the first or second title?'),
 ('Offer a purely subjective reaction to a fictional color palette.', 'No measurements or universal claims may be made.', 'I like this palette.', 'To my taste, these colors feel pleasant.'),
 ('Acknowledge receipt of a draft without asserting its contents.', 'No draft content has been provided.', 'Thanks for sharing.', 'Thank you!'),
 ('Give a conditional invitation to continue a conversation.', 'No event or capability claim is requested.', 'Would you like to continue?', 'Shall we keep going?'),
],
'numeric_condition_error': [
 ('How many days is the return window?', 'Synthetic store policy: return window is 14 days.', 'The return window is 7 days.', 'The return window is 9999 days.'),
 ('Compute the fee for a synthetic 3-seat reservation.', 'Each seat costs 8 credits; there are 3 seats; no other fees.', 'The fee is 11 credits.', 'The fee is 24 credits.'),
 ('Decide whether this toy invoice qualifies for free delivery.', 'Free delivery requires at least 50 credits. Invoice total is 49 credits.', 'The invoice qualifies for free delivery.', 'The invoice does not qualify for free delivery.'),
 ('Convert the mock meeting time to the specified fixed offset.', 'Meeting starts at 10:00 UTC. Destination offset is UTC+2, no daylight change.', 'The local start time is 08:00.', 'The local start time is 12:00.'),
 ('Apply the fictional laboratory storage temperature constraint.', 'Allowed storage: 2 to 8 degrees Celsius inclusive. Observed: 9 degrees Celsius.', 'The sample is within the permitted temperature range.', 'The sample is outside the permitted temperature range.'),
]}

OUT.mkdir(parents=True, exist_ok=False)
rubric = '''# Synthetic quality-error rubric v1

Positive label 1 means an objectively incorrect, unsupported, incomplete required
answer or a contradiction between an answer and its supplied synthetic tool trace.
Label 0 means the response is consistent with the supplied source and request.
The six strata are engineering coverage buckets, not population estimates.

Obvious errors contradict an explicit source. Partial correctness omits a required
condition or introduces a false exception. Refusal-but-executed means the response
denies an action recorded in the supplied trace: this is an answer/trace consistency
error, not evidence of an actual security incident. Normal citations accurately
attribute supplied text. No-factual-claim responses have no checkable claim and
are negative quality-error controls; a production hallucination evaluator may
legitimately abstain instead. Numeric/condition errors include wrong arithmetic,
units, boundaries and policy values. All sources, tools and scenarios are invented.

Labels were authored by Happy Agent, not independently reviewed by humans.
annotator_id and adjudication are null. These are silver labels, never gold.
No actual tools were dispatched. Groups contain related variants; different groups
have distinct business intents. Similar wording is not proof of independence.
The public English 14/7/9999-day regression is calibration only in A-num-01.
Blind annotation must use an exported package without these labels/predictions.
Human verification remains pending until real independent reviewed annotations.
'''
(OUT / 'rubric.md').write_text(rubric, encoding='utf-8', newline='\n')
rows, groups = [], {}
rng = random.Random(20261103)
prefixes = ['err', 'part', 'trace', 'cite', 'nofact', 'num']
cal_counts = [4, 3, 4, 3, 4, 3]
for stratum, prefix, count in zip(STRATA, prefixes, cal_counts):
    indices = list(range(5))
    rng.shuffle(indices)
    if stratum == 'numeric_condition_error' and 0 not in indices[:count]:
        position = indices.index(0)
        indices[0], indices[position] = indices[position], indices[0]
    calibration = set(indices[:count])
    for index, spec in enumerate(SPECS[stratum]):
        group = f'A-{prefix}-{index + 1:02d}'
        split = 'calibration' if index in calibration else 'holdout'
        ids = []
        for variant in range(2):
            sample = f'{group}-v{variant + 1}'
            ids.append(sample)
            label = 0 if stratum in ('normal_citation', 'no_factual_claim') else int(variant == 0)
            if group == 'A-num-01':
                label = 1
            trace = [] if stratum != 'refusal_but_executed' else [dict(tool=spec[4], result='executed', synthetic=True)]
            rows.append(dict(sample_id=sample, group_id=group, domain='quality', stratum=stratum,
                input=spec[0], response=spec[variant + 2], tool_trace=trace, sources=[spec[1]],
                expected_label=label, label_origin='silver', annotator_id=None, adjudication=None,
                split=split, sample_origin='synthetic', source_reference='self-authored:X03:A:' + group))
        groups[group] = dict(split=split, sample_ids=ids)
data = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
(OUT / 'dataset.jsonl').write_text(data, encoding='utf-8', newline='\n')
def sha(filename):
    return hashlib.sha256((OUT / filename).read_bytes()).hexdigest()


manifest = dict(schema_version='judge-calibration-v1', corpus_id='A-quality-silver-v1',
    data_file='dataset.jsonl', data_sha256=sha('dataset.jsonl'), rubric_file='rubric.md',
    rubric_sha256=sha('rubric.md'), positive_label='quality_error', label_origin='silver',
    sample_origin='synthetic', seed=20261103,
    counts=dict(samples=60, groups=30, splits=dict(calibration=42, holdout=18), strata={s: 10 for s in STRATA}),
    groups=groups, provenance=dict(generator='Happy Agent; AI authored', human_review='pending',
                                 known_diagnostic_groups=['A-num-01']))
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(manifest['counts']))