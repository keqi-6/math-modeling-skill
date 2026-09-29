/** Export validated Q1 fields into the official two-sheet result template. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const RUNTIME = 'C:/Users/35190/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const BUNDLED_MODULES = `${RUNTIME}/node/node_modules`;
const BUNDLED_PYTHON = `${RUNTIME}/python/python.exe`;
const OPERATION_MARKER = 'C:/Users/35190/.codex/plugins/cache/openai-primary-runtime/spreadsheets/26.905.11957/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs';
const TEMPLATE_SHA256 = '23b261b295c1b787d000eebbca6521c37075107b6fcf78724f8d395ce1798ff4';
const SHEETS = [
  { name: '温度', field: 'temperature_C', slug: 'temperature' },
  { name: '水分浓度', field: 'moisture_kg_kg', slug: 'moisture' },
];
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

function insist(condition, message) {
  if (!condition) throw new Error(message);
}

function parseArgs(argv) {
  const allowed = new Set(['input', 'output', 'template', 'preview-dir']);
  if (argv.includes('--help')) return null;
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i]?.replace(/^--/, '');
    insist(argv[i]?.startsWith('--') && allowed.has(key), `Unknown argument: ${argv[i]}`);
    insist(argv[i + 1] && !argv[i + 1].startsWith('--'), `Missing value for --${key}`);
    insist(!(key in args), `Repeated argument: --${key}`);
    args[key] = argv[i + 1];
  }
  for (const key of ['input', 'output', 'template']) insist(args[key], `Required: --${key}`);
  return args;
}

function samePath(a, b) {
  const normalize = p => process.platform === 'win32' ? path.resolve(p).toLowerCase() : path.resolve(p);
  return normalize(a) === normalize(b);
}

function validateInput(data) {
  insist(Array.isArray(data.time_s) && data.time_s.length === 1801, 'time_s must contain 1801 values.');
  insist(data.time_s.every((v, i) => Number.isInteger(v) && v === i), 'time_s must equal 0,1,...,1800.');
  insist(Array.isArray(data.radius_m) && data.radius_m.length === 21, 'radius_m must contain 21 values.');
  insist(data.radius_m.every((v, i) => Number.isFinite(v) && Math.abs(v - i / 1000) <= 1e-12),
    'radius_m must equal 0,0.001,...,0.02 m in ascending order.');
  for (const { field } of SHEETS) {
    insist(Array.isArray(data[field]) && data[field].length === 1801, `${field}: expected 1801 time rows.`);
    for (let i = 0; i < data[field].length; i++) {
      const row = data[field][i];
      insist(Array.isArray(row) && row.length === 21, `${field}[${i}]: expected 21 radial values.`);
      insist(row.every(v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) < 1e12),
        `${field}[${i}]: nonfinite, nonnumeric or unrepresentable four-decimal value.`);
    }
  }
}

function runPython(code, args) {
  const run = spawnSync(BUNDLED_PYTHON, ['-B', '-c', code, ...args], {
    encoding: 'utf8', windowsHide: true, maxBuffer: 8 * 1024 * 1024,
  });
  if (run.error) throw run.error;
  insist(run.status === 0, `Independent XML check failed: ${run.stderr || run.stdout}`);
  return JSON.parse(run.stdout);
}

const XML_TEMPLATE_CHECK = String.raw`
import sys, json, zipfile, xml.etree.ElementTree as ET, posixpath
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
relkey='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
with zipfile.ZipFile(sys.argv[1]) as z:
    w=ET.fromstring(z.read('xl/workbook.xml'))
    sheets=w.findall('m:sheets/m:sheet',ns)
    assert [s.get('name') for s in sheets]==['温度','水分浓度'], 'Unexpected template sheets or order'
    relationships=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    targets={r.get('Id'):r.get('Target') for r in relationships}
    for s in sheets:
        target=targets[s.get(relkey)]
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        root=ET.fromstring(z.read(target))
        assert not root.findall('.//m:f',ns), 'Template unexpectedly contains formulas'
        assert not root.findall('m:mergeCells/m:mergeCell',ns), 'Template unexpectedly contains merges'
    print(json.dumps({'status':'pass','sheets':[s.get('name') for s in sheets]}))
`;

// Read the saved XLSX independently. This verifier does not import artifact-tool
// or reuse the JS writer's rounded matrix.
const XML_RESULT_CHECK = String.raw`
import sys, json, math, zipfile, xml.etree.ElementTree as ET, posixpath, hashlib, re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
raw=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
book=Path(sys.argv[2]); ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
relkey='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
errors=[]; checks=[]; max_rounding=0.; max_saved_diff=0.; total=0
def column_number(label):
    n=0
    for c in label:n=n*26+ord(c)-64
    return n
def assert_equal(ok, label):
    if not ok:
        if len(errors)<25:errors.append(label)
with zipfile.ZipFile(book) as z:
    shared=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        shared=[''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
    styles=ET.fromstring(z.read('xl/styles.xml'))
    formats={n.get('numFmtId'):n.get('formatCode') for n in styles.findall('m:numFmts/m:numFmt',ns)}
    xfs=styles.findall('m:cellXfs/m:xf',ns)
    workbook=ET.fromstring(z.read('xl/workbook.xml'))
    sheets=workbook.findall('m:sheets/m:sheet',ns)
    assert_equal([s.get('name') for s in sheets]==['温度','水分浓度'],'sheet names/order')
    relationships=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    targets={r.get('Id'):r.get('Target') for r in relationships}
    for sheet,field in zip(sheets,['temperature_C','moisture_kg_kg']):
        target=targets[sheet.get(relkey)]
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        root=ET.fromstring(z.read(target))
        cells={c.get('r'):c for c in root.findall('m:sheetData/m:row/m:c',ns)}
        def value(address):
            c=cells.get(address)
            if c is None:return None
            if c.get('t')=='inlineStr':return ''.join(c.find('m:is',ns).itertext())
            n=c.find('m:v',ns)
            if n is None:return None
            if c.get('t')=='s':return shared[int(n.text)]
            if c.get('t')=='e':return 'EXCEL_ERROR:'+n.text
            try:return float(n.text)
            except ValueError:return n.text
        nonempty=[a for a in cells if value(a) is not None]
        coordinates=[(column_number(re.match(r'[A-Z]+',a).group()),int(re.search(r'\d+$',a).group())) for a in nonempty]
        assert_equal(len(nonempty)==1801*22,f'{sheet.get("name")}: nonempty count')
        assert_equal(max(c for c,r in coordinates)==22 and max(r for c,r in coordinates)==1801,f'{sheet.get("name")}: extent')
        assert_equal(value('A1')=='时间\\到药材中心的距离',f'{sheet.get("name")}: A1 label')
        assert_equal(not root.findall('.//m:f',ns),f'{sheet.get("name")}: unexpected formulas')
        assert_equal(not root.findall('m:mergeCells/m:mergeCell',ns),f'{sheet.get("name")}: unexpected merges')
        sheet_results=0; format_checks=0
        for j in range(21):
            col=chr(ord('B')+j)
            header=value(f'{col}1')
            assert_equal(isinstance(header,float) and abs(header-raw['radius_m'][j]*100)<=1e-12,f'{sheet.get("name")}: radius {col}')
        with localcontext() as ctx:
            ctx.prec=100
            for i in range(1,1801):
                row=i+1
                assert_equal(value(f'A{row}')==raw['time_s'][i],f'{sheet.get("name")}: time row {row}')
                for j in range(21):
                    address=f'{chr(ord("B")+j)}{row}'; v=value(address); source=raw[field][i][j]
                    # ECMAScript toFixed(4): nearest at four decimal places on
                    # the binary64 input, with exact ties away from zero.
                    expected=float(Decimal.from_float(float(source)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP))
                    good=isinstance(v,float) and math.isfinite(v)
                    assert_equal(good,f'{sheet.get("name")}: nonnumeric {address}')
                    if good:
                        difference=abs(v-expected);max_saved_diff=max(max_saved_diff,difference)
                        max_rounding=max(max_rounding,abs(v-source))
                        assert_equal(difference<=1e-12,f'{sheet.get("name")}: rounded value {address}')
                    c=cells.get(address)
                    if c is not None:
                        style=xfs[int(c.get('s','0'))]
                        assert_equal(formats.get(style.get('numFmtId'))=='0.0000',f'{sheet.get("name")}: number format {address}')
                        format_checks+=1
                    total+=1;sheet_results+=1
        checks.append({'sheet':sheet.get('name'),'rows':1801,'columns':22,'result_values':sheet_results,'number_formats_checked':format_checks})
print(json.dumps({'status':'pass' if not errors else 'fail','errors':errors,'sheets':checks,
 'result_values_checked':total,'maximum_saved_vs_rounded_difference':max_saved_diff,
 'maximum_absolute_export_rounding':max_rounding,
 'xlsx_sha256':hashlib.sha256(book.read_bytes()).hexdigest(),'xlsx_bytes':book.stat().st_size},ensure_ascii=False))
`;

async function loadArtifactTool(previewDir) {
  const moduleDir = path.join(previewDir, 'runtime');
  await fs.mkdir(moduleDir, { recursive: true });
  const link = path.join(moduleDir, 'node_modules');
  try {
    await fs.symlink(BUNDLED_MODULES, link, process.platform === 'win32' ? 'junction' : 'dir');
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
    insist(samePath(await fs.realpath(link), await fs.realpath(BUNDLED_MODULES)), 'Unexpected dependency junction target.');
  }
  const resolve = createRequire(path.join(moduleDir, 'resolve.cjs'));
  return import(pathToFileURL(resolve.resolve('@oai/artifact-tool')).href);
}

async function saveRender(workbook, sheetName, range, destination) {
  const blob = await workbook.render({ sheetName, range, scale: 1.5, format: 'png' });
  await fs.writeFile(destination, new Uint8Array(await blob.arrayBuffer()));
  return destination;
}

async function markOperation(previewDir, output) {
  const sentinel = path.join(previewDir, 'artifact_operation_started.json');
  try {
    const prior = JSON.parse(await fs.readFile(sentinel, 'utf8'));
    insist(prior.output === output && prior.status === 'success', 'Unexpected operation-marker receipt.');
    return 'already_marked_for_this_output';
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const marker = spawnSync(process.execPath, [OPERATION_MARKER, '--operation-kind', 'create',
    '--expected-output-count', '1', '--output-format', 'xlsx'], {
    cwd: path.dirname(path.dirname(OPERATION_MARKER)), encoding: 'utf8', windowsHide: true,
  });
  if (marker.error) throw marker.error;
  insist(marker.status === 0, `Artifact operation marker failed: ${marker.stderr || marker.stdout}`);
  await fs.writeFile(sentinel, JSON.stringify({ output, status: 'success' }, null, 2));
  return 'marked';
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args) {
    process.stdout.write('Usage: node src/Q1/export_workbook.mjs --input <JSON> --output output/Q1/result1.xlsx --template 附件/附件3/result1.xlsx [--preview-dir <temporary directory>]\n');
    return;
  }
  const input = path.resolve(args.input), output = path.resolve(args.output), template = path.resolve(args.template);
  insist(samePath(output, path.join(ROOT, 'output/Q1/result1.xlsx')), 'Output must be output/Q1/result1.xlsx in this project.');
  insist(samePath(template, path.join(ROOT, '附件/附件3/result1.xlsx')), 'Use the original project result1 template.');
  insist(!samePath(input, output) && !samePath(template, output), 'Output must not replace either source.');
  const inputBytes = await fs.readFile(input), templateBytes = await fs.readFile(template);
  insist(sha256(templateBytes) === TEMPLATE_SHA256, 'Official result1 template identity changed.');
  const data = JSON.parse(inputBytes.toString('utf8').replace(/^\uFEFF/, ''));
  validateInput(data);
  const templateCheck = runPython(XML_TEMPLATE_CHECK, [template]);
  const previewDir = args['preview-dir'] ? path.resolve(args['preview-dir']) : await fs.mkdtemp(path.join(os.tmpdir(), 'cumcm-q1-xlsx-'));
  const relativeTemp = path.relative(path.resolve(os.tmpdir()), previewDir);
  insist(relativeTemp && !relativeTemp.startsWith('..') && !path.isAbsolute(relativeTemp), 'preview-dir must be a child of the system temporary directory.');
  await fs.mkdir(previewDir, { recursive: true });
  const reportPath = path.join(previewDir, 'q1_export_report.json');
  const report = {
    status: 'started', input, output, template, preview_dir: previewDir,
    input_sha256: sha256(inputBytes), template_sha256: sha256(templateBytes),
    exporter_sha256: sha256(await fs.readFile(fileURLToPath(import.meta.url))),
    rounding: 'Number(binary64_value.toFixed(4)); displayed with 0.0000',
    template_check: templateCheck, previews: [],
  };
  try {
    const { FileBlob, SpreadsheetFile } = await loadArtifactTool(previewDir);
    const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
    for (const { name, slug } of SHEETS) {
      report.previews.push(await saveRender(workbook, name, 'A1:F5', path.join(previewDir, `template_${slug}.png`)));
    }
    report.operation_marker = await markOperation(previewDir, output);
    for (const { name, field } of SHEETS) {
      const sheet = workbook.worksheets.getItem(name);
      // Extend the supplied template's own styles before writing the full grid.
      sheet.getRange('B1:V1').copyFrom(sheet.getRange('B1'), 'all');
      sheet.getRange('A2:A1801').copyFrom(sheet.getRange('A2'), 'all');
      sheet.getRange('B2:V1801').copyFrom(sheet.getRange('B2'), 'all');
      sheet.getRange('B1:V1').values = [data.radius_m.map(v => Number((v * 100).toFixed(1)))];
      sheet.getRange('A2:A1801').values = data.time_s.slice(1).map(t => [t]);
      sheet.getRange('B2:V1801').values = data[field].slice(1).map(row => row.map(v => Number(v.toFixed(4))));
      sheet.getRange('A1:A1801').format.columnWidth = 27;
      sheet.getRange('B1:V1801').format.columnWidth = 11;
      sheet.getRange('A1:V1801').format.rowHeight = 16;
      sheet.getRange('B2:V1801').setNumberFormat('0.0000');
      sheet.getRange('A2:A1801').setNumberFormat('0');
      sheet.getRange('B1:V1').setNumberFormat('0.0');
      sheet.freezePanes.freezeRows(1);
      sheet.freezePanes.freezeColumns(1);
    }
    workbook.recalculate();
    report.in_memory_checks = [];
    for (const { name, field, slug } of SHEETS) {
      const sheet = workbook.worksheets.getItem(name);
      const inspected = await workbook.inspect({ kind: 'table', sheetId: name, range: 'A1:H5',
        include: 'values,formulas', tableMaxRows: 5, tableMaxCols: 8, maxChars: 3500 });
      report.in_memory_checks.push({ sheet: name, inspection: inspected.ndjson });
      const matrix = sheet.getRange('B2:V1801').values;
      let differences = 0;
      for (let i = 0; i < 1800; i++) for (let j = 0; j < 21; j++) {
        if (matrix[i][j] !== Number(data[field][i + 1][j].toFixed(4))) differences++;
      }
      insist(differences === 0, `${name}: in-memory result matrix differs from inputs.`);
      for (const [label, range] of [['first', 'A1:V8'], ['middle', 'A896:V905'], ['last', 'A1795:V1801']]) {
        report.previews.push(await saveRender(workbook, name, range, path.join(previewDir, `${slug}_${label}.png`)));
      }
    }
    const errors = await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
      options: { useRegex: true, maxResults: 25 }, maxChars: 3500, summary: 'Q1 result formula error scan' });
    report.formula_error_scan = errors.ndjson;
    await fs.mkdir(path.dirname(output), { recursive: true });
    const exported = await SpreadsheetFile.exportXlsx(workbook);
    await exported.save(output);
    report.independent_xml = runPython(XML_RESULT_CHECK, [input, output]);
    insist(report.independent_xml.status === 'pass', JSON.stringify(report.independent_xml.errors));
    insist(report.independent_xml.result_values_checked === 75600, 'Unexpected result-value count.');
    report.template_unchanged = sha256(await fs.readFile(template)) === report.template_sha256;
    report.input_unchanged = sha256(await fs.readFile(input)) === report.input_sha256;
    insist(report.template_unchanged && report.input_unchanged, 'Source changed during export.');
    report.status = 'pass';
    report.visual_review = 'Rendered previews require human/agent inspection before delivery.';
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    process.stdout.write(JSON.stringify({ status: report.status, output, report: reportPath,
      sha256: report.independent_xml.xlsx_sha256, values_checked: 75600, previews: report.previews }) + '\n');
  } catch (error) {
    report.status = 'fail';
    report.error = error.stack || String(error);
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    throw new Error(`${error.message}\nExport report: ${reportPath}`, { cause: error });
  }
}

main().catch(error => { process.stderr.write(`${error.stack || error}\n`); process.exitCode = 1; });
