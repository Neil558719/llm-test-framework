# Synthetic quality-error rubric v1

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
