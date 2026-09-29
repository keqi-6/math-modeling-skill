/** Q3: official one-sheet moisture workbook from the unchanged Q2 source NPZ.
 * Prepare/read-only template mode does not mark an authoring operation.
 * Invoke authoring only after path admission, native template review and runtime authorization.
 */
import fs from 'node:fs/promises';
import { createReadStream, constants as fsConstants } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const RUNTIME = 'C:/Users/35190/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const PYTHON = `${RUNTIME}/python/python.exe`;
const MODULES = `${RUNTIME}/node/node_modules`;
const MARKER = 'C:/Users/35190/.codex/plugins/cache/openai-primary-runtime/spreadsheets/26.905.11957/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs';
const TEMPLATE_SHA = '07e4793d620a7f899804c0298d49a16a197960440fd47f8bb780c57ec27e2859';
const INPUT_SHA = '79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b';
const METADATA_SHA = '1608daaf85666c495d9d62eaf19d07ff385c45bf66c58c598773e3769318871f';
const IMPLEMENTATION_SHA = '8365797324c7ceaadc7ca2cf27515d6ea14b325dba4f0a2ea2dd494b33b436f7';
const STRUCTURE_SHA = 'ff82989f40157cebb12a03bdb18e02d8411ede05c1cadf4e7f84c44898ac5fd8';
const OPERATION_ID = 'q3-result3-20260911';
const END = 206927;
const insist = (ok, message) => { if (!ok) throw new Error(message); };
const samePath = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

async function hashFile(p) {
  const h = crypto.createHash('sha256');
  for await (const block of createReadStream(p)) h.update(block);
  return h.digest('hex');
}
async function absent(p) {
  try { await fs.access(p); return false; } catch (e) { if (e.code === 'ENOENT') return true; throw e; }
}
function argsOf(argv) {
  const a = {};
  const allowed = new Set(['project-root', 'input', 'metadata', 'template', 'output', 'spec', 'preview-dir', 'template-reviewed-sha', 'rss-limit-mib']);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--preview-template') { insist(!a.previewTemplate, 'Repeated mode'); a.previewTemplate = true; continue; }
    if (argv[i] === '--help') return null;
    const key = argv[i].replace(/^--/, '');
    insist(argv[i].startsWith('--') && allowed.has(key) && !(key in a), `Unknown/repeated option ${argv[i]}`);
    insist(argv[i + 1] && !argv[i + 1].startsWith('--'), `Missing --${key}`);
    a[key] = argv[++i];
  }
  a.rssLimit = Number(a['rss-limit-mib'] ?? 2800);
  insist(Number.isFinite(a.rssLimit) && a.rssLimit > 0, 'rss-limit-mib must be positive');
  return a;
}
function run(executable, argv, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, argv, { windowsHide: true, ...options });
    let stdout = '', stderr = '';
    child.stdout.on('data', b => { stdout += b; });
    child.stderr.on('data', b => { stderr = (stderr + b).slice(-24000); });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve(stdout) : reject(new Error(`Child exit ${code}: ${stderr || stdout}`)));
  });
}
async function loadTool(temp) {
  const link = path.join(temp, 'node_modules');
  try { await fs.symlink(MODULES, link, 'junction'); }
  catch (e) { if (e.code !== 'EEXIST') throw e; insist(samePath(await fs.realpath(link), await fs.realpath(MODULES)), 'Dependency junction mismatch'); }
  const resolve = createRequire(path.join(temp, 'resolve.cjs'));
  return import(pathToFileURL(resolve.resolve('@oai/artifact-tool')).href);
}
async function render(workbook, range, destination) {
  const blob = await workbook.render({ sheetName: 'Sheet1', range, scale: 1.5, format: 'png' });
  await fs.writeFile(destination, new Uint8Array(await blob.arrayBuffer()));
  return destination;
}
async function markerOnce(temp, output) {
  const receipt = path.join(temp, 'artifact_operation_started.json');
  if (!(await absent(receipt))) {
    const prior = JSON.parse(await fs.readFile(receipt, 'utf8'));
    insist(prior.status === 'success' && prior.output === output && prior.operation_id === OPERATION_ID, 'Operation receipt mismatch');
    return 'already_marked_for_this_operation';
  }
  await run(process.execPath, [MARKER, '--operation-kind', 'create', '--expected-output-count', '1', '--output-format', 'xlsx'], { cwd: path.dirname(path.dirname(MARKER)) });
  await fs.writeFile(receipt, JSON.stringify({ status: 'success', output, operation_id: OPERATION_ID }));
  return 'marked';
}

// Read numerical source and write interchange/summary JSON only, never an XLSX.
const PREPARE = String.raw`
import sys,json,hashlib
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
import numpy as np
source,metadata,dest=map(Path,sys.argv[1:4])
end=206927
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()
def rounded(v):return format(Decimal.from_float(float(v)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP),'.4f')
meta=json.loads(metadata.read_text(encoding='utf-8-sig'))
assert meta['success'] is True and meta['grid_n']==10240 and meta['n_end']==end
assert meta['result_sha256']==digest(source)
times=np.r_[np.arange(60,end,60,dtype=np.int64),end]
table_times=np.r_[np.arange(21600,194401,21600,dtype=np.int64),end]
positions=np.array([0,5,10,15,20],dtype=np.int64)
assert len(times)==3449 and times[-2]==206880 and len(table_times)==10
with np.load(source,allow_pickle=False) as z:
    t,r=z['time_s'],z['radius_m']
    assert t.ndim==1 and len(t)>end and np.array_equal(t[:end+1],np.arange(end+1))
    assert r.shape==(21,) and np.max(np.abs(r-np.arange(21)/1000))<=1e-15
    c=z['moisture_kg_kg']
    assert c.dtype==np.dtype('float64') and c.shape==(len(t),21) and np.isfinite(c[:end+1]).all()
    selected=np.asarray(c[times],dtype='<f8',order='C')
    binary=dest/'moisture_kg_kg.f64le'
    binary.write_bytes(selected.tobytes(order='C'))
    table=c[np.ix_(table_times,positions)]
    summary={'schema_version':'1.0','question':'Q3','table_number':5,'input_npz':str(source),
      'input_npz_sha256':digest(source),'metadata':str(metadata),'metadata_sha256':digest(metadata),
      'terminal_time_s':end,'t_cross_s':meta['t_cross_s'],'n_end_s':end,'display_end_h':rounded(end/3600),
      'threshold_kg_kg':.15,'original_run_spec_sha256':meta['spec_sha256'],
      'time_s':table_times.tolist(),'time_h':(table_times/3600).tolist(),
      'row_roles':['6h','12h','18h','24h','30h','36h','42h','48h','54h','actual_terminal_second'],
      'radius_m':r[positions].tolist(),'radius_cm':(r[positions]*100).tolist(),
      'values':table.tolist(),'display_4dp':[[rounded(v) for v in row] for row in table],
      'units':'kg water/kg dry solid','rounding':'Decimal.from_float(binary64), ROUND_HALF_UP to 4 decimals'}
    summary['terminal_states']={}
    for label,instant in [('before_n_end',end-1),('n_end',end)]:
        summary['terminal_states'][label]={'time_s':instant,'max_moisture_kg_kg':float(z['max_moisture_kg_kg'][instant]),
          'argmax_radius_m':float(z['max_moisture_radius_m'][instant]),'argmax_node':int(z['max_moisture_node'][instant])}
    manifest={'schema':'q3_workbook_f64_v1','input_npz':str(source),'input_npz_sha256':digest(source),
      'metadata':str(metadata),'metadata_sha256':digest(metadata),'terminal_time_s':end,
      'time_s':times.tolist(),'radius_m':r.tolist(),'data_rows':len(times),'columns':22,
      'field':{'path':str(binary),'sha256':digest(binary),'dtype':'<f8','shape':[len(times),21]},
      'sampling':'60,120,...,206880 seconds, then the actual terminal second 206927; final gap 47 seconds'}
(dest/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(dest/'summary_values.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
`;

// Independent saved-XML comparison against a new read of the unchanged original NPZ.
// All stored whole-mesh maxima through the endpoint are inspected; the two terminal
// maxima are also recomputed from every node in their full snapshots.
const AUDIT = String.raw`
import sys,json,zipfile,hashlib,math,posixpath
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP,localcontext
import xml.etree.ElementTree as ET
import numpy as np
book,source,metadata,summary_path=map(Path,sys.argv[1:5])
M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RID='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
end=206927
times=list(range(60,end,60))+[end]
table_times=list(range(21600,194401,21600))+[end]
positions=[0,5,10,15,20]
errors=[];error_count=0;count=0;format_count=0;maximum_saved=0.;maximum_rounding=0.;row_count=0;cell_count=0
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def check(ok,label):
    global error_count
    if not bool(ok):
        error_count+=1
        if len(errors)<30:errors.append(label)
def rounded(v):return Decimal.from_float(float(v)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP)
meta=json.loads(metadata.read_text(encoding='utf-8-sig'))
summary=json.loads(summary_path.read_text(encoding='utf-8'));table5=summary['table5']
with np.load(source,allow_pickle=False) as z:
    seconds,r,c=z['time_s'],z['radius_m'],z['moisture_kg_kg']
    check(np.array_equal(seconds[:end+1],np.arange(end+1)),'Continuous source seconds through endpoint')
    check(c.shape==(len(seconds),21) and c.dtype==np.dtype('float64') and np.isfinite(c[:end+1]).all() and np.min(c[:end+1])>0,'Finite positive float64 source moisture field')
    maxima=z['max_moisture_kg_kg']
    check(maxima.shape==seconds.shape and np.isfinite(maxima).all(),'All-node maximum series axis and finite values')
    first=np.flatnonzero(maxima[:end+1]<.15)
    check(first.size>0 and int(first[0])==end,'First strictly passing stored all-node maximum occurs at 206927')
    mesh=z['mesh_radius_m']
    snapshot_times=z['snapshot_time_s'];snapshots=z['moisture_snapshots']
    check(mesh.shape==(10241,) and np.max(np.abs(mesh-np.linspace(0,.02,10241)))<=1e-15,'Full mesh radius axis')
    terminal={}
    for role,t in [('before_n_end',end-1),('n_end',end)]:
        index=meta['snapshot_roles'][role];values=snapshots[index]
        check(snapshot_times[index]==t and values.shape==(10241,) and np.isfinite(values).all(),'Complete terminal snapshot '+role)
        maximum=float(values.max());argmax=int(values.argmax())
        check(abs(maximum-float(maxima[t]))<=1e-13,'Recomputed all-node maximum agrees with series '+role)
        check(np.max(np.abs(values[::512]-c[t]))<=1e-12,'Snapshot agrees with output radii '+role)
        check(maximum>=.15 if t==end-1 else maximum<.15,'Strict terminal comparison '+role)
        terminal[role]={'time_s':t,'max_moisture_kg_kg':maximum,'argmax_node':argmax,'argmax_radius_m':float(mesh[argmax]),'strictly_below_0_15':bool(maximum<.15),'nodes_checked':10241}
        published=summary['terminal_states'][role]
        check(published['time_s']==t and abs(published['max_moisture_kg_kg']-maximum)<=1e-13 and published['argmax_node']==argmax and abs(published['argmax_radius_m']-float(mesh[argmax]))<=1e-15,'Summary terminal state '+role)
    post=maxima[end:]
    largest_increase=max(0.,float(np.max(np.diff(post)))) if len(post)>1 else 0.
    check(np.all(post<.15) and largest_increase<=5e-9,'No return across threshold and no recorded increase beyond numerical allowance after endpoint')
    event_index=meta['snapshot_roles']['threshold_crossing'];event_max=float(snapshots[event_index].max())
    check(snapshot_times[event_index]==meta['t_cross_s'] and abs(event_max-.15)<=5e-10,'Stored crossing snapshot at threshold')
    terminal.update({'status':'pass' if error_count==0 else 'fail','first_passing_integer_s':int(first[0]) if first.size else None,
      'stored_maxima_samples_checked':end+1,'criterion':'max over all 10241 nodes C(t) < 0.15, evaluated without rounding',
      'post_endpoint_samples_checked':len(post),'post_endpoint_observed_end_s':int(seconds[-1]),'maximum_post_endpoint_upward_step':largest_increase,'post_endpoint_upward_allowance':5e-9,
      'crossing_time_s':meta['t_cross_s'],'crossing_snapshot_max_moisture':event_max,
      'scope':'First integer from the stored whole-mesh maxima series, with independent recomputation over every node at 206926 and 206927 s. Exact retained numerical trajectory, not an exact continuous-PDE stopping-time proof.'})
    check(meta['n_end']==end and meta['threshold_kg_kg']==.15,'Metadata agrees with independently checked endpoint')
    check(table5['time_s']==table_times and table5['radius_m']==r[positions].tolist(),'Table5 axes')
    check(summary['workbook_sampling']['time_s']==times and summary['workbook_sampling']['radius_m']==r.tolist(),'Summary complete workbook time/radius axes')
    check(summary['input_npz_sha256']==digest(source),'Table5 original NPZ identity')
    check(summary['n_end_s']==end and summary['t_cross_s']==meta['t_cross_s'] and summary['display_end_h']==format(rounded(end/3600),'.4f') and summary['threshold_kg_kg']==.15,'Summary terminal time semantics')
    raw=c[np.ix_(table_times,positions)];table_cells=[]
    for i,t in enumerate(table_times):
        for j,position in enumerate(positions):
            want=float(raw[i,j]);display=format(rounded(want),'.4f')
            ok=table5['values'][i][j]==want and table5['display_4dp'][i][j]==display
            check(ok,'Table5 value '+str((i,j)))
            table_cells.append({'time_s':t,'radius_cm':float(r[position]*100),'raw_float64':want,'display_4dp':display,'passed':ok})
    with zipfile.ZipFile(book) as archive:
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():strings=[''.join(t.text or '' for t in si.iter(M+'t')) for si in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        styles=ET.fromstring(archive.read('xl/styles.xml'))
        formats={f.get('numFmtId'):f.get('formatCode') for f in styles.findall(M+'numFmts/'+M+'numFmt')}
        xfs=styles.findall(M+'cellXfs/'+M+'xf');fonts=styles.findall(M+'fonts/'+M+'font')
        sheets=ET.fromstring(archive.read('xl/workbook.xml')).findall(M+'sheets/'+M+'sheet')
        check(len(sheets)==1 and sheets[0].get('name')=='Sheet1','Exactly the original Sheet1')
        rels={x.get('Id'):x.get('Target') for x in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        target=rels[sheets[0].get(RID)]
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        dimension=None;pane=None;formula_count=0;merge_count=0;hidden=0;sheetdata=None
        with archive.open(target) as stream,localcontext() as context:
            context.prec=100
            for event,element in ET.iterparse(stream,events=('start','end')):
                if event=='start':
                    if element.tag==M+'sheetData':sheetdata=element
                    continue
                if element.tag==M+'dimension':dimension=element.get('ref')
                elif element.tag==M+'pane':pane=dict(element.attrib)
                elif element.tag==M+'mergeCell':merge_count+=1
                elif element.tag==M+'col':hidden+=element.get('hidden')=='1'
                elif element.tag==M+'row':
                    row=int(element.get('r','0'));row_count+=1;hidden+=element.get('hidden')=='1'
                    check(row==row_count,'Sequential worksheet row')
                    cells=element.findall(M+'c');cell_count+=len(cells)
                    check([x.get('r') for x in cells]==[chr(65+j)+str(row) for j in range(22)],'Exact A:V cells at row '+str(row))
                    for j,cell in enumerate(cells):
                        value_node=cell.find(M+'v');ctype=cell.get('t');value=None
                        formula_count+=cell.find(M+'f') is not None
                        if ctype=='inlineStr':value=''.join(t.text or '' for t in cell.iter(M+'t'))
                        elif ctype=='s' and value_node is not None:value=strings[int(value_node.text)]
                        elif ctype in (None,'n') and value_node is not None:
                            try:value=float(value_node.text)
                            except ValueError:pass
                        if row==1:
                            check(value==('时间\\到药材中心的距离' if j==0 else round(j/10-.1,1)), 'Original title and radius header '+str(cell.get('r')))
                            if j==0:
                                xf=xfs[int(cell.get('s','0'))];font=fonts[int(xf.get('fontId','0'))];alignment=xf.find(M+'alignment')
                                check(font.find(M+'name').get('val')=='宋体' and float(font.find(M+'sz').get('val'))==10 and alignment is not None and alignment.get('horizontal')=='center','Original title font and alignment')
                        elif 2<=row<=len(times)+1:
                            if j==0:check(value==times[row-2],'Minute sample or exact terminal time at row '+str(row))
                            elif 1<=j<=21:
                                source_value=float(c[times[row-2],j-1]);expected=float(rounded(source_value));count+=1
                                numeric=type(value) is float and math.isfinite(value)
                                check(numeric and value==expected,'Independently rounded moisture '+str(cell.get('r')))
                                if numeric:
                                    maximum_saved=max(maximum_saved,abs(value-expected));maximum_rounding=max(maximum_rounding,abs(value-source_value))
                                style=int(cell.get('s','0'));format_count+=1
                                check(style<len(xfs) and formats.get(xfs[style].get('numFmtId'))=='0.0000','Four decimal number format '+str(cell.get('r')))
                        else:check(False,'Out-of-range row')
                    element.clear()
                    if sheetdata is not None:sheetdata.remove(element)
    check(row_count==3450 and cell_count==75900,'Full worksheet cell count')
    check(count==72429 and format_count==72429,'Every result value and number format checked')
    # The dimension element is optional; exact sequential A:V cells were checked above.
    check(dimension is None or dimension=='A1:V3450','Declared used range when present')
    check(pane is not None and pane.get('state')=='frozen' and pane.get('topLeftCell')=='B2','Freeze first row and time column')
    check(formula_count==0 and merge_count==0 and hidden==0,'No formulas, merged cells or hidden data')
result={'status':'pass' if error_count==0 else 'fail','error_count':error_count,'errors':errors,
  'sheet':'Sheet1','rows':row_count,'data_rows':3449,'columns':22,'total_cells':cell_count,
  'actual_used_range':'A1:V3450','declared_dimension':dimension,'used_range_basis':'Every row index and every A:V cell coordinate checked, plus exact total row/cell counts',
  'result_values_checked':count,'number_formats_checked':format_count,'maximum_saved_vs_rounded_difference':maximum_saved,
  'maximum_absolute_export_rounding':maximum_rounding,'terminal_verification':terminal,
  'table5':{'values_checked':len(table_cells),'cells':table_cells},'xlsx_sha256':digest(book),'xlsx_bytes':book.stat().st_size,
  'input_npz_sha256':digest(source),'metadata_sha256':digest(metadata),'summary_sha256':digest(summary_path)}
print(json.dumps(result,ensure_ascii=False))
`;

async function place(staged, target, expected) {
  const intermediate = path.join(path.dirname(target), `.${path.basename(target)}.staging`);
  insist(await absent(target) && await absent(intermediate), `Preserve existing output/staging identity: ${target}`);
  await fs.copyFile(staged, intermediate, fsConstants.COPYFILE_EXCL);
  insist(await hashFile(intermediate) === expected, `Destination-side checksum mismatch: ${target}`);
  await fs.rename(intermediate, target);
  insist(await hashFile(target) === expected, `Final placement checksum mismatch: ${target}`);
}

async function main() {
  const args = argsOf(process.argv.slice(2));
  if (!args) { console.log('node export_workbook.mjs --project-root <project> [--preview-template] [--template-reviewed-sha <actual visually reviewed template SHA>] [--input output/Q2/run_n10240_startsafe.npz] [--metadata output/Q2/run_n10240_startsafe.json] [--spec planning/Q3/model_spec.md] [--output output/Q3/result3.xlsx] [--template 附件/附件3/result3.xlsx] [--preview-dir <TEMP child>] [--rss-limit-mib 2800]'); return; }
  const root = path.resolve(args['project-root'] ?? ROOT);
  const template = path.resolve(root, args.template ?? '附件/附件3/result3.xlsx');
  const input = path.resolve(root, args.input ?? 'output/Q2/run_n10240_startsafe.npz');
  const metadata = path.resolve(root, args.metadata ?? 'output/Q2/run_n10240_startsafe.json');
  const specification = path.resolve(root, args.spec ?? 'planning/Q3/model_spec.md');
  const output = path.resolve(root, args.output ?? 'output/Q3/result3.xlsx');
  const auditOutput = path.join(root, 'output/Q3/workbook_audit.json');
  const summaryOutput = path.join(root, 'output/Q3/summary_values.json');
  const temp = path.resolve(args['preview-dir'] ?? path.join(os.tmpdir(), 'cumcm-q3-workbook'));
  const relative = path.relative(os.tmpdir(), temp);
  insist(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Previews must stay inside TEMP');
  insist(samePath(template, path.join(root, '附件/附件3/result3.xlsx')) && await hashFile(template) === TEMPLATE_SHA, 'Original template identity mismatch');
  insist(samePath(output, path.join(root, 'output/Q3/result3.xlsx')), 'Only the official Q3 output is admitted');
  await fs.mkdir(temp, { recursive: true });
  const { FileBlob, SpreadsheetFile } = await loadTool(temp);
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
  if (args.previewTemplate) {
    const preview = await render(workbook, 'A1:F5', path.join(temp, 'template_native.png'));
    const receipt = { template, template_sha256: TEMPLATE_SHA, preview, preview_sha256: await hashFile(preview), scope: 'Native read-only original template rendering; actual image review remains required; no authoring marker.' };
    await fs.writeFile(path.join(temp, 'template_preview.json'), JSON.stringify(receipt, null, 2));
    console.log(JSON.stringify(receipt)); return;
  }
  insist(args['template-reviewed-sha'] === TEMPLATE_SHA, 'Caller must first actually view the read-only native template preview and pass its reviewed SHA');
  const previewReceipt = JSON.parse(await fs.readFile(path.join(temp, 'template_preview.json'), 'utf8'));
  insist(previewReceipt.template_sha256 === TEMPLATE_SHA && await hashFile(previewReceipt.preview) === previewReceipt.preview_sha256, 'Template preview identity mismatch');
  for (const p of [output, auditOutput, summaryOutput]) insist(await absent(p), `Do not overwrite existing Q3 identity: ${p}`);
  const started = performance.now();
  const reportPath = path.join(temp, 'q3_export_report.json');
  const report = { status: 'started', question: 'Q3', input, metadata, output, template, template_sha256: TEMPLATE_SHA,
    exporter_sha256: await hashFile(fileURLToPath(import.meta.url)), operation_id: OPERATION_ID, memory_samples: [], native_previews: [],
    units: { time: 's', radius: 'cm', moisture: 'kg water/kg dry solid' },
    rounding: 'Number(binary64.toFixed(4)) stored as numeric values with 0.0000 format; independent Decimal-based audit',
    source_reuse: 'The original Q2 NPZ remains in output/Q2 under its original identity; no model rerun or renamed source copy.' };
  const memory = label => { const sample = { label, ...process.memoryUsage() }; report.memory_samples.push(sample); insist(sample.rss <= args.rssLimit * 1048576, `RSS limit exceeded at ${label}`); };
  try {
    insist(samePath(specification, path.join(root, 'planning/Q3/model_spec.md')), 'Use the admitted Q3 specification');
    const state = JSON.parse(await fs.readFile(path.join(root, '.modeling/state.json'), 'utf8'));
    const specificationHash = await hashFile(specification), specRecord = state.artifacts['planning/Q3/model_spec.md'];
    insist(specRecord?.identity_class === 'frozen' && specRecord?.status === 'validated' && specRecord?.sha256 === specificationHash, 'The actual Q3 specification must be frozen and validated before authoring');
    report.specification = { path: specification, sha256: specificationHash, identity_class: specRecord.identity_class, status: specRecord.status };
    insist(await hashFile(input) === INPUT_SHA && await hashFile(metadata) === METADATA_SHA, 'Original accepted source identity mismatch');
    const priorPath = path.join(root, 'output/Q2/verification_implementation.json');
    insist(await hashFile(priorPath) === IMPLEMENTATION_SHA, 'Frozen implementation evidence identity changed');
    const prior = JSON.parse(await fs.readFile(priorPath, 'utf8'));
    insist(prior.passed === true && prior.checks.length && prior.checks.every(c => c.passed === true), 'Prior implementation report is not passing');
    insist(prior.details.run_identities.some(r => r.result_sha256 === INPUT_SHA && r.metadata_sha256 === METADATA_SHA), 'Prior evidence does not bind this exact NPZ and metadata');
    report.prior_verification = { path: priorPath, sha256: IMPLEMENTATION_SHA, passed_checks: prior.checks.length, reuse: 'Existing evidence identity only; verifier not executed' };
    const structurePath = path.join(root, 'output/Q2/verification_structure.json');
    insist(await hashFile(structurePath) === STRUCTURE_SHA, 'Frozen structural evidence identity changed');
    const structure = JSON.parse(await fs.readFile(structurePath, 'utf8'));
    insist(structure.passed === true && structure.checks.length && structure.checks.every(c => c.passed === true), 'Prior structural report is not passing');
    report.prior_structural_verification = { path: structurePath, sha256: STRUCTURE_SHA, passed_checks: structure.checks.length, reuse: 'Existing structural/sensitivity evidence only; no new numerical run' };
    const reusedNames = ['run_n5120_startsafe.npz', 'run_n10240_tight_startsafe.npz', 'run_n10240_last_startsafe.npz'];
    report.reused_comparison_sources = [];
    for (const name of reusedNames) {
      const binding = prior.details.run_identities.find(r => path.basename(r.result) === name);
      insist(binding && await hashFile(binding.result) === binding.result_sha256 && await hashFile(binding.metadata) === binding.metadata_sha256, `Reused comparison identity mismatch: ${name}`);
      report.reused_comparison_sources.push(binding);
    }
    const manifest = JSON.parse(await run(PYTHON, ['-B', '-c', PREPARE, input, metadata, temp]));
    report.input_manifest = manifest;
    insist(manifest.data_rows === 3449 && manifest.terminal_time_s === END, 'Wrong Q3 output schedule');
    const summaryPath = path.join(temp, 'summary_values.json');
    const preparedSummary = JSON.parse(await fs.readFile(summaryPath, 'utf8'));
    const table5Keys = ['table_number', 'time_s', 'time_h', 'row_roles', 'radius_m', 'radius_cm', 'values', 'display_4dp', 'units', 'rounding'];
    const table5 = Object.fromEntries(table5Keys.map(k => [k, preparedSummary[k]]));
    for (const key of table5Keys) delete preparedSummary[key];
    const refinementNames = ['full_process_spatial_temperature_C', 'full_process_spatial_moisture_kg_kg', 'full_process_temporal_temperature_C', 'full_process_temporal_moisture_kg_kg', 'spatial_crossing_time_difference', 'temporal_crossing_time_difference'];
    const refinementChecks = prior.checks.filter(c => refinementNames.includes(c.name));
    insist(refinementChecks.length === 6 && refinementChecks.every(c => c.passed === true), 'Required prior refinement evidence missing');
    const summaryObject = { ...preparedSummary, specification: report.specification, table5,
      source_reuse: report.source_reuse, generator_sha256: report.exporter_sha256,
      workbook_sampling: { time_s: manifest.time_s, radius_m: manifest.radius_m, radius_cm: manifest.radius_m.map(v => Number((100 * v).toFixed(1))), data_rows: 3449, final_interval_s: 47 },
      refinement: { source: report.prior_verification, checks: refinementChecks, integer_endpoint_stability: prior.details.integer_endpoint_stability, reuse: 'Existing complete-domain comparisons reused; no recomputation or new ODE runtime claimed' },
      sensitivity: { source: report.prior_structural_verification, ...structure.details.long_time_boundary_sensitivity },
      reused_comparison_sources: report.reused_comparison_sources,
      mean_threshold_counterexample: { equal_weight_concentrations: [.16, .01], mean: (.16 + .01) / 2, maximum: .16, threshold: .15, conclusion: 'An average below 0.15 does not imply every region is below 0.15.' } };
    await fs.writeFile(summaryPath, JSON.stringify(summaryObject, null, 2));
    const sheet = workbook.worksheets.getItem('Sheet1');
    report.operation_marker = await markerOnce(temp, output);
    sheet.getRange('B1:V1').copyFrom(sheet.getRange('B1'), 'all');
    sheet.getRange('B1:V1').values = [manifest.radius_m.map(v => Number((v * 100).toFixed(1)))];
    sheet.getRange('B1:V1').setNumberFormat('0.0');
    sheet.getRange('A1').format.columnWidth = 29;
    sheet.getRange('B1:V1').format.columnWidth = 11;
    sheet.getRange('A1:V1').format.rowHeight = 17;
    const bytes = await fs.readFile(manifest.field.path);
    insist(await hashFile(manifest.field.path) === manifest.field.sha256 && bytes.length === 3449 * 21 * 8, 'Interchange identity mismatch');
    for (let first = 0; first < manifest.data_rows; first += 1024) {
      const rows = Math.min(1024, manifest.data_rows - first), start = first + 2, stop = first + rows + 1;
      const times = sheet.getRange(`A${start}:A${stop}`), body = sheet.getRange(`B${start}:V${stop}`);
      times.copyFrom(sheet.getRange('A2'), 'all'); body.copyFrom(sheet.getRange('B2'), 'all');
      times.values = manifest.time_s.slice(first, first + rows).map(t => [t]);
      body.values = Array.from({ length: rows }, (_, i) => Array.from({ length: 21 }, (_, j) => Number(bytes.readDoubleLE(((first + i) * 21 + j) * 8).toFixed(4))));
      times.setNumberFormat('0'); body.setNumberFormat('0.0000'); sheet.getRange(`A${start}:V${stop}`).format.rowHeight = 17;
      memory(`rows:${first + rows}/3449`);
    }
    sheet.freezePanes.freezeRows(1); sheet.freezePanes.freezeColumns(1);
    workbook.recalculate();
    report.native_inspections = [];
    for (const [label, range] of [['first', 'A1:V8'], ['last', 'A3443:V3450']]) {
      report.native_inspections.push({ label, range, ndjson: (await workbook.inspect({ kind: 'table', sheetId: 'Sheet1', range, include: 'values,formulas', tableMaxRows: 8, tableMaxCols: 22, maxChars: 7000 })).ndjson });
      report.native_previews.push(await render(workbook, range, path.join(temp, `moisture_${label}.png`)));
    }
    report.formula_error_scan = (await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 25 }, maxChars: 2500 })).ndjson;
    memory('before_export');
    const exported = await SpreadsheetFile.exportXlsx(workbook);
    memory('after_export');
    const staged = path.join(temp, 'result3.xlsx'), summary = path.join(temp, 'summary_values.json');
    await exported.save(staged);
    report.independent_verification = JSON.parse(await run(PYTHON, ['-B', '-c', AUDIT, staged, input, metadata, summary]));
    insist(report.independent_verification.status === 'pass', JSON.stringify(report.independent_verification.errors));
    insist(report.independent_verification.result_values_checked === 72429 && report.independent_verification.table5.values_checked === 50, 'Incomplete independent coverage');
    insist(await hashFile(input) === INPUT_SHA && await hashFile(metadata) === METADATA_SHA && await hashFile(template) === TEMPLATE_SHA && await hashFile(specification) === specificationHash, 'Source changed during export');
    await fs.mkdir(path.dirname(output), { recursive: true });
    await place(staged, output, report.independent_verification.xlsx_sha256);
    await place(summary, summaryOutput, report.independent_verification.summary_sha256);
    report.elapsed_s = (performance.now() - started) / 1000;
    const audit = { schema: 'q3_workbook_audit_v1', status: 'awaiting_visual_review', data_status: 'pass', output,
      input_npz: input, input_npz_sha256: INPUT_SHA, metadata, metadata_sha256: METADATA_SHA,
      template, template_sha256: TEMPLATE_SHA, specification: report.specification, exporter_sha256: report.exporter_sha256, prior_verification: report.prior_verification, prior_structural_verification: report.prior_structural_verification,
      terminal_time_s: END, schedule: manifest.sampling, units: report.units, rounding: report.rounding,
      independent_verification: report.independent_verification, native_previews: report.native_previews,
      native_render_scope: 'First and last ranges rendered from the complete artifact-tool authoring workbook; saved XLSX independently checked in full through XML',
      visual_review: { status: 'pending', note: 'Actually view both final native previews before acceptance; terminal displayed 0.1500 is rounding, while the strict endpoint check uses unrounded all-node values.' },
      memory_samples: report.memory_samples, elapsed_s: report.elapsed_s, detailed_report: reportPath };
    await fs.writeFile(auditOutput, JSON.stringify(audit, null, 2), { flag: 'wx' });
    report.status = 'pass';
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ status: 'pass', output, audit: auditOutput, summary: summaryOutput, sha256: report.independent_verification.xlsx_sha256, values_checked: 72429, table5_values_checked: 50, elapsed_s: report.elapsed_s, visual_review: 'pending' }));
  } catch (e) {
    report.status = 'fail'; report.error = e.stack || String(e); report.elapsed_s = (performance.now() - started) / 1000;
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2)); throw e;
  }
}
main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
