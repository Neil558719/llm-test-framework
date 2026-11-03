"""Validate the versioned synthetic silver corpus shared by projects A and B."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

STRATA = ('obvious_error', 'partially_correct', 'refusal_but_executed',
          'normal_citation', 'no_factual_claim', 'numeric_condition_error')
REQUIRED = ('sample_id', 'group_id', 'domain', 'stratum', 'input', 'response',
            'tool_trace', 'sources', 'expected_label', 'label_origin', 'annotator_id',
            'adjudication', 'split', 'sample_origin', 'source_reference')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _decode(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def read_json(path):
    return _decode(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def load_corpus(manifest_path):
    path = Path(manifest_path).resolve()
    manifest = read_json(path)
    for key in ('schema_version', 'corpus_id', 'data_file', 'data_sha256', 'rubric_file',
                'rubric_sha256', 'positive_label', 'label_origin', 'sample_origin',
                'seed', 'counts', 'groups', 'provenance'):
        _require(key in manifest, 'missing manifest field: ' + key)
    _require(manifest['schema_version'] == 'judge-calibration-v1', 'unsupported corpus schema')
    _require(manifest['label_origin'] == 'silver' and manifest['sample_origin'] == 'synthetic',
             'this version accepts synthetic silver labels only')
    _require(manifest['positive_label'] in ('quality_error', 'security_violation'), 'unknown label direction')
    _require(manifest['provenance'].get('human_review') == 'pending', 'unverified human provenance')
    _require(bool(manifest['provenance'].get('generator')), 'missing generator provenance')
    _require(type(manifest['seed']) is int, 'seed must be an integer')
    paths = []
    for key, hash_key in (('data_file', 'data_sha256'), ('rubric_file', 'rubric_sha256')):
        file = (path.parent / manifest[key]).resolve()
        _require(file.parent == path.parent, 'corpus assets must be adjacent files')
        _require(digest(file.read_bytes()) == manifest[hash_key], key + ' hash mismatch')
        paths.append(file)
    rows = []
    for line in paths[0].read_text(encoding='utf-8').splitlines():
        _require(bool(line.strip()), 'blank corpus record')
        row = _decode(line)
        _require(isinstance(row, dict), 'record must be an object')
        _require(all(k in row for k in REQUIRED), 'missing record field')
        for key in ('sample_id', 'group_id', 'domain', 'input', 'response', 'source_reference'):
            _require(isinstance(row[key], str) and bool(row[key].strip()), 'invalid record ' + key)
        _require(row['stratum'] in STRATA, 'unknown stratum')
        _require(row['split'] in ('calibration', 'holdout'), 'invalid split')
        _require(type(row['expected_label']) is int and row['expected_label'] in (0, 1), 'invalid label')
        _require(row['label_origin'] == 'silver' and row['sample_origin'] == 'synthetic', 'invalid label provenance')
        _require(row['annotator_id'] is None and row['adjudication'] is None, 'fabricated human provenance')
        _require(isinstance(row['tool_trace'], list) and all(isinstance(x, dict) for x in row['tool_trace']),
                 'tool_trace must contain objects')
        _require(isinstance(row['sources'], list) and all(isinstance(x, str) for x in row['sources']),
                 'sources must contain strings')
        domain = 'quality' if manifest['positive_label'] == 'quality_error' else 'security'
        _require(row['domain'] == domain, 'domain and positive label disagree')
        rows.append(row)
    ids = [r['sample_id'] for r in rows]
    _require(len(ids) == len(set(ids)), 'duplicate sample ID')
    observed: Dict[str, List[Dict[str, Any]]] = {}
    templates: Dict[str, str] = {}
    for row in rows:
        template = re.sub(r'\d+', '<n>', row['input'].casefold())
        template = ' '.join(template.split())
        if template in templates:
            _require(templates[template] == row['group_id'], 'same input template crosses groups')
        templates[template] = row['group_id']
        observed.setdefault(row['group_id'], []).append(row)
    _require(set(observed) == set(manifest['groups']), 'group inventory mismatch')
    for group, members in observed.items():
        spec = manifest['groups'][group]
        _require(len(members) == 2, 'each group must have two variants')
        _require(len({r['stratum'] for r in members}) == 1, 'group crosses strata')
        _require({r['split'] for r in members} == {spec['split']}, 'group split leakage')
        _require(len(spec['sample_ids']) == 2 and set(spec['sample_ids']) == {r['sample_id'] for r in members},
                 'sample inventory mismatch')
    counts = dict(samples=len(rows), groups=len(observed),
                  splits=dict(Counter(r['split'] for r in rows)), strata=dict(Counter(r['stratum'] for r in rows)))
    _require(counts == manifest['counts'], 'count inventory mismatch')
    for group in manifest['provenance'].get('known_diagnostic_groups', []):
        _require(group in observed and manifest['groups'][group]['split'] == 'calibration',
                 'public diagnostic must remain calibration only')
    return manifest, rows


def load_predictions(path, manifest, selected):
    import math
    data = read_json(path)
    _require(data.get('schema_version') == 'calibration-predictions-v1', 'unsupported prediction schema')
    for key in ('corpus_id', 'data_sha256', 'rubric_sha256'):
        _require(data.get(key) == manifest[key], 'prediction binding mismatch: ' + key)
    _require(isinstance(data.get('model'), str) and bool(data['model'].strip()), 'model identity required')
    prompt_hash = data.get('prompt_sha256')
    _require(isinstance(prompt_hash, str) and len(prompt_hash) == 64 and
             all(x in '0123456789abcdef' for x in prompt_hash), 'prompt SHA256 required')
    predictions = data.get('predictions')
    _require(isinstance(predictions, list), 'predictions must be a list')
    indexed = {}
    for prediction in predictions:
        sample = prediction.get('sample_id')
        _require(isinstance(sample, str) and sample not in indexed, 'invalid or duplicate prediction ID')
        status = prediction.get('status')
        _require(status in ('evaluated', 'abstain', 'error', 'not_executed'), 'invalid prediction status')
        label, score = prediction.get('label'), prediction.get('score')
        _require(label is None or (type(label) is int and label in (0, 1)), 'invalid predicted label')
        _require(score is None or (type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1),
                 'score must be finite and between zero and one')
        _require((status == 'evaluated' and (label is not None or score is not None)) or
                 (status != 'evaluated' and label is None and score is None), 'status/value mismatch')
        indexed[sample] = prediction
    _require(set(indexed) == {r['sample_id'] for r in selected}, 'predictions must exactly cover the selected split')
    return data, indexed


def blind_package(manifest, rows):
    fields = ('domain', 'input', 'response', 'tool_trace', 'sources')
    records = []
    for row in rows:
        record = {key: row[key] for key in fields}
        # Hide answer-coded group prefixes and coverage-stratum names too.
        record.update(sample_id=digest(('annotation:' + row['sample_id']).encode())[:24],
                      group_id=digest(('annotation:' + row['group_id']).encode())[:24], annotation=None)
        records.append(record)
    return dict(schema_version='calibration-blind-v1', corpus_id=manifest['corpus_id'],
                data_sha256=manifest['data_sha256'], rubric_sha256=manifest['rubric_sha256'],
                human_verified=False, annotation_status='pending',
                instructions='Independent annotation required; do not consult silver labels or model outputs.',
                records=records)