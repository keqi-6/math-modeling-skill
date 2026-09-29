/** Q2: populate the official two-sheet template from an accepted NPZ.
 * Public artifact-tool APIs; no streaming-export claim.
 * Invoke only after project path admission and the authoring runtime plan.
 */
import fs from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const RUNTIME = 'C:/Users/35190/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const PYTHON = `${RUNTIME}/python/python.exe`;
const MODULES = `${RUNTIME}/node/node_modules`;
const MARKER = 'C:/Users/35190/.codex/plugins/cache/openai-primary-runtime/spreadsheets/26.905.11957/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs';
const TEMPLATE_SHA = '23b261b295c1b787d000eebbca6521c37075107b6fcf78724f8d395ce1798ff4';
const SHEETS = [
  { name: '温度', field: 'temperature_C', slug: 'temperature', unit: '°C' },
  { name: '水分浓度', field: 'moisture_kg_kg', slug: 'moisture', unit: 'kg water/kg dry solid' },
];
const insist = (ok, message) => { if (!ok) throw new Error(message); };
const samePath = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

async function hashFile(p) {
  const hash = crypto.createHash('sha256');
  for await (const chunk of createReadStream(p)) hash.update(chunk);
  return hash.digest('hex');
}

function parseArgs(argv) {
  if (argv.includes('--help')) return null;
  const allowed = new Set(['input', 'metadata', 'output', 'template', 'preview-dir', 'project-root', 'chunk-rows', 'rss-limit-mib']);
  const a = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i]?.replace(/^--/, '');
    insist(argv[i]?.startsWith('--') && allowed.has(key), `Unknown option: ${argv[i]}`);
    insist(argv[i + 1] && !argv[i + 1].startsWith('--') && !(key in a), `Missing/repeated --${key}`);
    a[key] = argv[i + 1];
  }
  for (const key of ['input', 'metadata', 'output', 'template']) insist(a[key], `Required --${key}`);
  a.chunkRows = Number(a['chunk-rows'] ?? 1024);
  insist(Number.isInteger(a.chunkRows) && a.chunkRows >= 32 && a.chunkRows <= 8192, 'chunk-rows must be an integer in 32..8192.');
  a.rssLimitMiB = Number(a['rss-limit-mib'] ?? 0);
  insist(Number.isFinite(a.rssLimitMiB) && a.rssLimitMiB >= 0, 'rss-limit-mib must be nonnegative (0 means observe only).');
  return a;
}

function run(executable, argv, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, argv, { windowsHide: true, ...options });
    let stdout = '', stderr = '';
    child.stdout.on('data', data => { stdout += data; });
    child.stderr.on('data', data => { stderr = (stderr + data).slice(-24000); });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve(stdout) : reject(new Error(`Child exit ${code}: ${stderr || stdout}`)));
  });
}

// Only numerical interchange files are written by Python. No spreadsheet authoring.
const PREPARE = String.raw`
import sys, json, zipfile, hashlib, shutil, math
from pathlib import Path
import numpy as np
source, metadata, dest = map(Path, sys.argv[1:4])
chunk = int(sys.argv[4])
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()
srcsha, metasha = digest(source), digest(metadata)
meta=json.loads(metadata.read_text(encoding='utf-8-sig'))
end=meta.get('n_end')
assert type(end) is int and 1 <= end <= 1048575, 'metadata.n_end must fit the one-header-row Excel worksheet'
fields=['temperature_C','moisture_kg_kg']
manifest={'schema':'q2_workbook_f64_v1','input_npz':str(source),'input_npz_sha256':srcsha,
 'metadata':str(metadata),'metadata_sha256':metasha,'n_end':end,'time_start_s':1,'time_step_s':1,
 'row_count':end,'columns_per_field':21,'fields':{},
 'termination_interpretation':'n_end is supplied by the accepted solver metadata, not inferred from the 21 output radii'}
with zipfile.ZipFile(source) as z:
    for name in ['time_s','radius_m']+fields:
        assert z.namelist().count(name+'.npy')==1, 'Missing/duplicate NPZ array '+name
    t=np.load(z.open('time_s.npy'),allow_pickle=False)
    r=np.load(z.open('radius_m.npy'),allow_pickle=False)
    assert t.ndim==1 and len(t)>end and np.isfinite(t).all()
    for first in range(0,len(t),chunk):
        assert np.array_equal(t[first:first+chunk],np.arange(first,min(first+chunk,len(t)))), 'Noncontiguous seconds'
    assert r.shape==(21,) and np.allclose(r,np.arange(21)/1000,rtol=0,atol=1e-12), 'Wrong physical radii'
    manifest['radius_m']=r.tolist();manifest['common_end_s']=int(t[-1]);manifest['source_rows']=len(t)
    del r
    for field in fields:
        staged=dest/(field+'.source.npy')
        with z.open(field+'.npy') as stream, staged.open('wb') as target:
            shutil.copyfileobj(stream,target,8*1024*1024)
        data=np.load(staged,mmap_mode='r',allow_pickle=False)
        assert data.shape==(len(t),21) and data.dtype.kind=='f' and data.dtype.itemsize==8, field+' must be float64 [time,21]'
        binary=dest/(field+'.f64le')
        minimum=float('inf');maximum=-float('inf')
        with binary.open('wb') as target:
            for first in range(1,end+1,chunk):
                block=np.asarray(data[first:min(first+chunk,end+1)],dtype='<f8',order='C')
                assert np.isfinite(block).all() and np.max(np.abs(block))<1e12, field+' has invalid output values'
                minimum=min(minimum,float(np.min(block)));maximum=max(maximum,float(np.max(block)))
                target.write(block.tobytes(order='C'))
        if field=='moisture_kg_kg':
            assert np.all(data[end]<.15), 'Final exported radial samples do not satisfy strict <0.15'
        manifest['fields'][field]={'path':str(binary),'sha256':digest(binary),'dtype':'<f8','shape':[end,21],
            'bytes':binary.stat().st_size,'minimum':minimum,'maximum':maximum}
        del data,block
        staged.unlink()
assert digest(source)==srcsha and digest(metadata)==metasha, 'Accepted source changed during extraction'
(dest/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
`;

// Independent, bounded-memory XML traversal. All output numbers and format IDs
// are checked against the unrounded binary64 interchange, not the writer matrix.
const AUDIT = String.raw`
import sys, json, zipfile, hashlib, math, posixpath
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP, localcontext
import xml.etree.ElementTree as ET
import numpy as np
manifest=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
book=Path(sys.argv[2]);end=manifest['n_end']
M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RID='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
errors=[];error_count=0;total=0;maximum_saved_diff=0.;maximum_rounding=0.;sheet_reports=[]
def check(ok,label):
    global error_count
    if not ok:
        error_count+=1
        if len(errors)<30:errors.append(label)
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
with zipfile.ZipFile(book) as z:
    strings=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        root=ET.fromstring(z.read('xl/sharedStrings.xml'))
        strings=[''.join(t.text or '' for t in si.iter(M+'t')) for si in root]
    styles=ET.fromstring(z.read('xl/styles.xml'))
    formats={s.get('numFmtId'):s.get('formatCode') for s in styles.findall(M+'numFmts/'+M+'numFmt')}
    xfs=styles.findall(M+'cellXfs/'+M+'xf')
    sheets=ET.fromstring(z.read('xl/workbook.xml')).findall(M+'sheets/'+M+'sheet')
    check([s.get('name') for s in sheets]==['温度','水分浓度'],'Exactly two sheets in official order')
    rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    for sheet,field in zip(sheets,['temperature_C','moisture_kg_kg']):
        name=sheet.get('name'); info=manifest['fields'][field]
        check(digest(info['path'])==info['sha256'],field+' binary identity')
        data=np.memmap(info['path'],dtype='<f8',mode='r',shape=(end,21))
        target=rels[sheet.get(RID)]
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        row_count=0;count=0;format_count=0;formula_count=0;max_row=0;cells_count=0;last_row=0
        dimension=None;pane=None;merge_count=0;hidden_rows=0;hidden_cols=0;sheetdata=None
        with z.open(target) as stream,localcontext() as ctx:
            ctx.prec=100
            for event,element in ET.iterparse(stream,events=('start','end')):
                if event=='start':
                    if element.tag==M+'sheetData':sheetdata=element
                    continue
                if element.tag==M+'dimension':dimension=element.get('ref')
                elif element.tag==M+'pane':pane=dict(element.attrib)
                elif element.tag==M+'mergeCell':merge_count+=1
                elif element.tag==M+'col' and element.get('hidden')=='1':hidden_cols+=1
                elif element.tag==M+'row':
                    row=int(element.get('r','0'));row_count+=1;max_row=max(max_row,row)
                    check(row==last_row+1,name+' sequential row '+str(row));last_row=row
                    hidden_rows+=element.get('hidden')=='1'
                    cells=element.findall(M+'c');cells_count+=len(cells)
                    expected_addresses=[chr(65+j)+str(row) for j in range(22)]
                    check([c.get('r') for c in cells]==expected_addresses,name+' exact A:V row '+str(row))
                    for j,c in enumerate(cells):
                        address=c.get('r');ctype=c.get('t')
                        formula_count+=c.find(M+'f') is not None
                        value_node=c.find(M+'v')
                        if ctype=='inlineStr':value=''.join(t.text or '' for t in c.iter(M+'t'))
                        elif ctype=='s':value=strings[int(value_node.text)] if value_node is not None else None
                        elif ctype in (None,'n') and value_node is not None:
                            try:value=float(value_node.text)
                            except ValueError:value=None
                        else:value=None
                        if row==1:
                            expected='时间\\到药材中心的距离' if j==0 else round(manifest['radius_m'][j-1]*100,1) if j<=21 else None
                            check(value==expected,name+' header '+str(address))
                        elif 2<=row<=end+1 and j==0:check(value==row-1,name+' integer second '+str(address))
                        elif 2<=row<=end+1 and 1<=j<=21:
                            source=float(data[row-2,j-1]);count+=1;total+=1
                            expected=float(Decimal.from_float(source).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP))
                            numeric=type(value) is float and math.isfinite(value)
                            check(numeric,name+' numeric '+str(address))
                            if numeric:
                                difference=abs(value-expected)
                                maximum_saved_diff=max(maximum_saved_diff,difference)
                                maximum_rounding=max(maximum_rounding,abs(value-source))
                                check(value==expected,name+' rounded binary64 '+str(address))
                            index=int(c.get('s','0'));format_count+=1
                            check(index<len(xfs) and formats.get(xfs[index].get('numFmtId'))=='0.0000',name+' four-decimal format '+str(address))
                        else:check(False,name+' out-of-range cell '+str(address))
                    element.clear()
                    if sheetdata is not None:sheetdata.remove(element)
        check(row_count==end+1 and max_row==end+1,name+' extent rows')
        check(cells_count==(end+1)*22,name+' exact cell count')
        check(dimension=='A1:V'+str(end+1),name+' dimension')
        check(count==end*21 and format_count==end*21,name+' result and format coverage')
        check(formula_count==0 and merge_count==0 and hidden_rows==0 and hidden_cols==0,name+' formulas/merges/hidden data')
        check(pane is not None and pane.get('topLeftCell')=='B2' and pane.get('state')=='frozen',name+' freeze panes')
        sheet_reports.append({'sheet':name,'rows':row_count,'columns':22,'cells':cells_count,
            'result_values':count,'number_formats_checked':format_count,'formula_count':formula_count,
            'dimension':dimension,'pane':pane})
        del data
check(digest(manifest['input_npz'])==manifest['input_npz_sha256'],'NPZ unchanged')
check(digest(manifest['metadata'])==manifest['metadata_sha256'],'metadata unchanged')
result={'status':'pass' if error_count==0 else 'fail','error_count':error_count,'errors':errors,
 'sheets':sheet_reports,'result_values_checked':total,'maximum_saved_vs_rounded_difference':maximum_saved_diff,
 'maximum_absolute_export_rounding':maximum_rounding,'xlsx_sha256':digest(book),'xlsx_bytes':book.stat().st_size,
 'input_npz_sha256':manifest['input_npz_sha256'],'metadata_sha256':manifest['metadata_sha256']}
print(json.dumps(result,ensure_ascii=False))
`;

async function loadTool(temp) {
  const link = path.join(temp, 'node_modules');
  try { await fs.symlink(MODULES, link, 'junction'); }
  catch (e) { if (e.code !== 'EEXIST') throw e; insist(samePath(await fs.realpath(link), await fs.realpath(MODULES)), 'Dependency junction mismatch.'); }
  const resolve = createRequire(path.join(temp, 'resolve.cjs'));
  return import(pathToFileURL(resolve.resolve('@oai/artifact-tool')).href);
}

async function markerOnce(temp, output) {
  const receipt = path.join(temp, 'artifact_operation_started.json');
  try {
    const prior = JSON.parse(await fs.readFile(receipt, 'utf8'));
    insist(prior.output === output && prior.status === 'success', 'Operation receipt mismatch.');
    return 'already_marked_for_this_output';
  } catch (e) { if (e.code !== 'ENOENT') throw e; }
  await run(process.execPath, [MARKER, '--operation-kind', 'create', '--expected-output-count', '1', '--output-format', 'xlsx'], { cwd: path.dirname(path.dirname(MARKER)) });
  await fs.writeFile(receipt, JSON.stringify({ output, status: 'success' }));
  return 'marked';
}

async function render(wb, name, range, destination) {
  const blob = await wb.render({ sheetName: name, range, scale: 1.5, format: 'png' });
  await fs.writeFile(destination, new Uint8Array(await blob.arrayBuffer()));
  return destination;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args) {
    console.log('node export_workbook.mjs --input <NPZ> --metadata <JSON with n_end> --output output/Q2/result2.xlsx --template 附件/附件3/result2.xlsx [--project-root <project>] [--preview-dir <TEMP child>] [--chunk-rows 1024] [--rss-limit-mib 0]');
    return;
  }
  const root = path.resolve(args['project-root'] ?? PROJECT_ROOT);
  const input = path.resolve(root, args.input), metadata = path.resolve(root, args.metadata);
  const output = path.resolve(root, args.output), template = path.resolve(root, args.template);
  const auditOutput = path.join(root, 'output/Q2/workbook_audit.json');
  insist(samePath(output, path.join(root, 'output/Q2/result2.xlsx')), 'Only the admitted Q2 result2.xlsx output is allowed.');
  insist(samePath(template, path.join(root, '附件/附件3/result2.xlsx')), 'Use the original Q2 template.');
  insist(await hashFile(template) === TEMPLATE_SHA, 'Official template identity mismatch.');
  const temp = args['preview-dir'] ? path.resolve(args['preview-dir']) : path.join(os.tmpdir(), 'cumcm-q2-workbook');
  const relative = path.relative(os.tmpdir(), temp);
  insist(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Preview/interchange directory must be inside TEMP.');
  await fs.mkdir(temp, { recursive: true });
  const reportPath = path.join(temp, 'q2_export_report.json');
  const report = { status: 'started', input, metadata, output, audit_output: auditOutput, template, preview_dir: temp, template_sha256: TEMPLATE_SHA,
    exporter_sha256: await hashFile(fileURLToPath(import.meta.url)), previews: [], memory_samples: [],
    chunk_rows: args.chunkRows, rss_limit_mib: args.rssLimitMiB,
    memory_scope: 'Source interchange and Python XML rows are bounded. The artifact-tool workbook and export remain in memory; no streaming/flush API was documented.',
    rounding: 'Number(binary64_value.toFixed(4)), numeric cells with 0.0000 display format',
    units: { time: 's', radius: 'cm', temperature: '°C', moisture: 'kg water/kg dry solid' },
  };
  const memory = label => {
    const sample = { label, ...process.memoryUsage() };
    report.memory_samples.push(sample);
    insist(!args.rssLimitMiB || sample.rss <= args.rssLimitMiB * 1048576, `RSS limit exceeded at ${label}; no cell flush is available.`);
  };
  try {
    const manifest = JSON.parse(await run(PYTHON, ['-B', '-c', PREPARE, input, metadata, temp, String(args.chunkRows)]));
    report.input_manifest = manifest;
    const { FileBlob, SpreadsheetFile } = await loadTool(temp);
    const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
    report.template_inspection = (await workbook.inspect({ kind: 'sheet', include: 'id,name', maxChars: 2000 })).ndjson;
    for (const { name, slug } of SHEETS) report.previews.push(await render(workbook, name, 'A1:F5', path.join(temp, `template_${slug}.png`)));
    // The original template is already rendered and visually reviewed during preparation.
    // This is the first actual authoring step, so mark exactly here, never in preparation.
    report.operation_marker = await markerOnce(temp, output);
    for (const { name, field } of SHEETS) {
      const sheet = workbook.worksheets.getItem(name);
      sheet.getRange('B1:V1').copyFrom(sheet.getRange('B1'), 'all');
      sheet.getRange('B1:V1').values = [manifest.radius_m.map(v => Number((v * 100).toFixed(1)))];
      sheet.getRange('B1:V1').setNumberFormat('0.0');
      sheet.getRange('A1').format.columnWidth = 29;
      sheet.getRange('B1:V1').format.columnWidth = 11;
      sheet.getRange('A1:V1').format.rowHeight = 17;
      const source = await fs.open(manifest.fields[field].path, 'r');
      try {
        for (let first = 0; first < manifest.n_end; first += args.chunkRows) {
          const rows = Math.min(args.chunkRows, manifest.n_end - first);
          const bytes = Buffer.allocUnsafe(rows * 21 * 8);
          let read = 0;
          while (read < bytes.length) {
            const part = await source.read(bytes, read, bytes.length - read, first * 21 * 8 + read);
            insist(part.bytesRead > 0, 'Unexpected end of binary interchange.'); read += part.bytesRead;
          }
          const start = first + 2, stop = first + rows + 1;
          const body = sheet.getRange(`B${start}:V${stop}`), times = sheet.getRange(`A${start}:A${stop}`);
          // Extend the template convention only over the current populated block.
          times.copyFrom(sheet.getRange('A2'), 'all');
          body.copyFrom(sheet.getRange('B2'), 'all');
          times.values = Array.from({ length: rows }, (_, i) => [first + i + 1]);
          body.values = Array.from({ length: rows }, (_, i) => Array.from({ length: 21 }, (_, j) => Number(bytes.readDoubleLE((i * 21 + j) * 8).toFixed(4))));
          times.setNumberFormat('0'); body.setNumberFormat('0.0000');
          sheet.getRange(`A${start}:V${stop}`).format.rowHeight = 17;
          if (first === 0 || first + rows === manifest.n_end || Math.floor(first / args.chunkRows) % 16 === 0) {
            memory(`${field}:${first + rows}/${manifest.n_end}`);
            console.log(JSON.stringify({ progress: field, rows_written: first + rows, total_rows: manifest.n_end, rss_mib: Math.round(process.memoryUsage().rss / 1048576) }));
          }
        }
      } finally { await source.close(); }
      sheet.freezePanes.freezeRows(1); sheet.freezePanes.freezeColumns(1);
    }
    workbook.recalculate();
    report.inspections = [];
    const last = manifest.n_end + 1, middle = Math.max(2, Math.floor(last / 2) - 3);
    const ranges = [['first', `A1:V${Math.min(last, 8)}`], ['middle', `A${middle}:V${Math.min(last, middle + 7)}`], ['last', `A${Math.max(2, last - 7)}:V${last}`]];
    for (const { name, slug } of SHEETS) {
      for (const [label, range] of ranges) {
        report.inspections.push({ sheet: name, label, range, ndjson: (await workbook.inspect({ kind: 'table', sheetId: name, range, include: 'values,formulas', tableMaxRows: 8, tableMaxCols: 22, maxChars: 7000 })).ndjson });
        report.previews.push(await render(workbook, name, range, path.join(temp, `${slug}_${label}.png`)));
      }
    }
    report.formula_error_scan = (await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 25 }, maxChars: 3000, summary: 'Q2 final formula error scan' })).ndjson;
    memory('before_export');
    await fs.mkdir(path.dirname(output), { recursive: true });
    const exported = await SpreadsheetFile.exportXlsx(workbook);
    memory('after_export_before_save');
    // Export the single workbook to TEMP, where library inspection sidecars stay.
    // Move this same file into its admitted location only after the XML audit.
    const stagedWorkbook = path.join(temp, 'result2.xlsx');
    await exported.save(stagedWorkbook);
    report.independent_xml = JSON.parse(await run(PYTHON, ['-B', '-c', AUDIT, path.join(temp, 'input_manifest.json'), stagedWorkbook]));
    insist(report.independent_xml.status === 'pass', JSON.stringify(report.independent_xml.errors));
    insist(report.independent_xml.result_values_checked === manifest.n_end * 42, 'Incomplete full XML coverage.');
    insist(await hashFile(template) === TEMPLATE_SHA, 'Original template changed.');
    await fs.rename(stagedWorkbook, output);
    insist(await hashFile(output) === report.independent_xml.xlsx_sha256, 'Workbook changed during final placement.');
    report.status = 'pass';
    report.visual_review = 'Eight native renders were created; final first/middle/last previews must be actually viewed before delivery.';
    const audit = {
      schema: 'q2_workbook_audit_v1', status: 'awaiting_visual_review', data_status: 'pass',
      output, template, input_npz: input, metadata,
      input_npz_sha256: manifest.input_npz_sha256, metadata_sha256: manifest.metadata_sha256,
      template_sha256: TEMPLATE_SHA, exporter_sha256: report.exporter_sha256,
      n_end: manifest.n_end, units: report.units, rounding: report.rounding,
      independent_xml: report.independent_xml, native_previews: report.previews,
      visual_review: { status: 'pending', note: report.visual_review },
      detailed_export_report: reportPath,
    };
    await fs.writeFile(auditOutput, JSON.stringify(audit, null, 2));
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ status: report.status, output, audit: auditOutput, report: reportPath, n_end: manifest.n_end, values_checked: manifest.n_end * 42, sha256: report.independent_xml.xlsx_sha256 }));
  } catch (e) {
    report.status = 'fail'; report.error = e.stack || String(e);
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    throw e;
  }
}

main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
