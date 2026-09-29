/** Q2: export only seconds 1..10800 from the accepted NPZ to the official template.
 * Public artifact-tool APIs; no streaming-export claim.
 * Invoke only after project path admission and the authoring runtime plan.
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
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const PYTHON = `${RUNTIME}/python/python.exe`;
const MODULES = `${RUNTIME}/node/node_modules`;
const MARKER = 'C:/Users/35190/.codex/plugins/cache/openai-primary-runtime/spreadsheets/26.905.11957/skills/spreadsheets/container_tools/mark_artifact_operation_started.mjs';
const TEMPLATE_SHA = '23b261b295c1b787d000eebbca6521c37075107b6fcf78724f8d395ce1798ff4';
const OUTPUT_END_S = 10800;
const SCOPE_SHA = 'b1c9b1344521bd91b40fdca49bf8cab700b245432b7263985f40331ea32c6d7e';
const OPERATION_ID = 'q2-submission-first-3h-20260911';
const INPUT_SHA = '79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b';
const METADATA_SHA = '1608daaf85666c495d9d62eaf19d07ff385c45bf66c58c598773e3769318871f';
const PRIOR_WORKBOOK_SHA = '74065813689079c52b87b9a83cbb3f4a4f4eed64921828c2a15cad5a16b094e1';
const PRIOR_AUDIT_SHA = '01ae2499d710c16fbbab5d21d667e479baa945247522bc021efed349bdabaef9';
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
  const flags = argv.filter(v => v === '--from-validated-history');
  insist(flags.length <= 1, 'Repeated history mode flag.');
  argv = argv.filter(v => v !== '--from-validated-history');
  const allowed = new Set(['input', 'metadata', 'output', 'template', 'preview-dir', 'project-root', 'chunk-rows', 'rss-limit-mib', 'failure-evidence', 'marker-receipt', 'interchange-manifest']);
  const a = { fromValidatedHistory: flags.length === 1 };
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
end=10800
assert isinstance(meta,dict), 'Expected source provenance metadata object'
fields=['temperature_C','moisture_kg_kg']
manifest={'schema':'q2_submission_first_3h_f64_v1','input_npz':str(source),'input_npz_sha256':srcsha,
 'metadata':str(metadata),'metadata_sha256':metasha,'output_end_s':end,'time_start_s':1,'time_step_s':1,
 'row_count':end,'columns_per_field':21,'fields':{},
 'output_scope':'User-confirmed Q2 submission: integer seconds 1..10800 inclusive; source metadata is provenance only'}
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
book=Path(sys.argv[2]);end=manifest['output_end_s']
assert end==10800, 'Q2 submission must end at three hours'
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
    insist(prior.output === output && prior.status === 'success' && prior.operation_id === OPERATION_ID && prior.output_end_s === OUTPUT_END_S, 'Operation receipt mismatch.');
    return 'already_marked_for_this_output';
  } catch (e) { if (e.code !== 'ENOENT') throw e; }
  await run(process.execPath, [MARKER, '--operation-kind', 'edit', '--expected-output-count', '1', '--output-format', 'xlsx'], { cwd: path.dirname(path.dirname(MARKER)) });
  await fs.writeFile(receipt, JSON.stringify({ output, status: 'success', operation_id: OPERATION_ID, output_end_s: OUTPUT_END_S }));
  return 'marked';
}

async function render(wb, name, range, destination) {
  const blob = await wb.render({ sheetName: name, range, scale: 1.5, format: 'png' });
  await fs.writeFile(destination, new Uint8Array(await blob.arrayBuffer()));
  return destination;
}

// Recovery is deliberately limited to the observed complete-XLSX export memory
// failure. Small projection imports/renders still use the available artifact tool.
const HISTORY_FAILURE_SHA = 'f7ec4e1632c8834c94ccf1d3122422fc56cda5affed7c59eef36f887f87da6d3';
const HISTORY_FAILURE_EXPORTER_SHA = '66df61a390278f79ce6baa3c525d2dbbb3f9d8fc874ce3a149f45c2849addcc0';

const VERIFY_INTERCHANGE = String.raw`
import sys,json,zipfile,hashlib
from pathlib import Path
import numpy as np
m=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));end=m['output_end_s']
assert end==10800 and m['row_count']==end and m['columns_per_field']==21
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
assert digest(m['input_npz'])==m['input_npz_sha256']
assert digest(m['metadata'])==m['metadata_sha256']
checked=0;fields=[]
with zipfile.ZipFile(m['input_npz']) as z:
    t=np.load(z.open('time_s.npy'),allow_pickle=False)
    r=np.load(z.open('radius_m.npy'),allow_pickle=False)
    assert np.array_equal(t[:end+1],np.arange(end+1)) and len(t)==m['source_rows']
    assert r.shape==(21,) and np.array_equal(r,np.array(m['radius_m']))
    for field in ['temperature_C','moisture_kg_kg']:
        info=m['fields'][field]
        assert info['dtype']=='<f8' and info['shape']==[end,21] and info['bytes']==end*21*8
        assert Path(info['path']).stat().st_size==info['bytes'] and digest(info['path'])==info['sha256']
        source=np.load(z.open(field+'.npy'),allow_pickle=False)
        assert source.shape==(len(t),21) and source.dtype.kind=='f' and source.dtype.itemsize==8
        data=np.memmap(info['path'],dtype='<f8',mode='r',shape=(end,21))
        assert np.isfinite(data).all() and np.array_equal(source[1:end+1],data),field+' interchange differs from NPZ'
        checked+=int(data.size);fields.append({'field':field,'values_compared':int(data.size),'maximum_difference':0.0,'binary_sha256':info['sha256']})
        del data,source
print(json.dumps({'status':'pass','values_compared':checked,'output_start_s':1,'output_end_s':end,'fields':fields,
 'input_npz_sha256':m['input_npz_sha256'],'metadata_sha256':m['metadata_sha256']}))
`;

// Keep every retained worksheet row as the exact original XML bytes. Only the
// dimension and removal of rows beyond the agreed scope change worksheet XML.
const CROP_HISTORY = String.raw`
import sys,json,zipfile,hashlib,copy,re,time
from pathlib import Path
source=Path(sys.argv[1]);target=Path(sys.argv[2]);end=int(sys.argv[3]);old_last=206928;last=end+1
assert end==10800 and not target.exists()
started=time.perf_counter();sheets=['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml'];sheet_reports=[]
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
source_sha=digest(source)
with zipfile.ZipFile(source) as original,zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as out:
    names=original.namelist();assert len(names)==len(set(names)) and all(n in names for n in sheets)
    out.comment=original.comment;unchanged={}
    for info in original.infolist():
        if info.filename not in sheets:
            content=original.read(info.filename);out.writestr(copy.copy(info),content)
            unchanged[info.filename]=hashlib.sha256(content).hexdigest();continue
        new_info=copy.copy(info);new_info.file_size=0
        retained_hash=hashlib.sha256();footer_hash=hashlib.sha256();kept=0;count=0;buffer=b'';stage='header'
        with original.open(info.filename) as reader,out.open(new_info,'w') as writer:
            while True:
                block=reader.read(65536)
                if not block:break
                if stage=='footer':writer.write(block);footer_hash.update(block);continue
                buffer+=block
                if stage=='header':
                    offset=buffer.find(b'<sheetData>')
                    if offset<0:
                        assert len(buffer)<=1048576,'Unexpected worksheet header size';continue
                    offset+=len(b'<sheetData>');header=buffer[:offset];buffer=buffer[offset:]
                    expected=b'<dimension ref="A1:V206928" />'
                    assert header.count(expected)==1,'Unexpected validated-history dimension'
                    updated=header.replace(expected,b'<dimension ref="A1:V10801" />')
                    writer.write(updated);stage='rows'
                while stage=='rows' and buffer:
                    if buffer.startswith(b'</sheetData>'):
                        assert count==old_last,'Wrong historical row count'
                        writer.write(buffer);footer_hash.update(buffer);buffer=b'';stage='footer';break
                    if b'</sheetData>'.startswith(buffer):break
                    if len(buffer)<5:break
                    assert buffer.startswith(b'<row '),'Unexpected content between historical rows'
                    stop=buffer.find(b'</row>')
                    if stop<0:
                        assert len(buffer)<=1048576,'Unexpected historical row size';break
                    stop+=len(b'</row>');row=buffer[:stop];buffer=buffer[stop:]
                    opening=row[:row.find(b'>')+1];match=re.search(rb'\br="([0-9]+)"',opening)
                    assert match is not None
                    count+=1;assert int(match.group(1))==count,'Nonsequential historical row'
                    if count<=last:writer.write(row);retained_hash.update(row);kept+=1
            assert stage=='footer' and not buffer and kept==last and count==old_last
        sheet_reports.append({'member':info.filename,'source_rows_read':count,'retained_rows':kept,
            'removed_rows':count-kept,'retained_row_xml_sha256':retained_hash.hexdigest(),
            'original_header_sha256':hashlib.sha256(header).hexdigest(),'updated_header_sha256':hashlib.sha256(updated).hexdigest(),
            'unchanged_footer_sha256':footer_hash.hexdigest(),'dimension':'A1:V10801'})
with zipfile.ZipFile(source) as original,zipfile.ZipFile(target) as saved:
    assert saved.namelist()==original.namelist() and saved.comment==original.comment
    for name,sha in unchanged.items():assert hashlib.sha256(saved.read(name)).hexdigest()==sha
    # Independent row-byte readback also checks retained content/styles and footer.
    for item in sheet_reports:
        with saved.open(item['member']) as reader:
            content=reader.read()  # Revised worksheet is about 10 MB, bounded by 10801 rows.
        start=content.index(b'<sheetData>')+len(b'<sheetData>');stop=content.index(b'</sheetData>',start)
        assert hashlib.sha256(content[:start]).hexdigest()==item['updated_header_sha256']
        assert hashlib.sha256(content[start:stop]).hexdigest()==item['retained_row_xml_sha256']
        assert hashlib.sha256(content[stop:]).hexdigest()==item['unchanged_footer_sha256']
        del content
assert digest(source)==source_sha
print(json.dumps({'status':'pass','authoring_route':'crop_validated_history_XML_rows','source_sha256':source_sha,
 'output_end_s':end,'sheets':sheet_reports,'unchanged_zip_members':unchanged,'unchanged_member_count':len(unchanged),
 'changed_members':sheets,'change_scope':'Only worksheet dimension and omission of rows 10802..206928; retained row bytes and other ZIP member contents unchanged',
 'sha256':digest(target),'bytes':target.stat().st_size,'elapsed_s':time.perf_counter()-started}))
`;

const HISTORY_PROJECTIONS = String.raw`
import sys,json,zipfile,io,base64,copy
from pathlib import Path
import xml.etree.ElementTree as ET
book=Path(sys.argv[1]);end=int(sys.argv[2]);last=end+1
M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
ET.register_namespace('',M[1:-1]);ET.register_namespace('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships')
starts={'first':2,'last':max(2,last-7)}
ranges={label:list(range(start,min(last,start+7)+1)) for label,start in starts.items()}
required={1}|{r for rows in ranges.values() for r in rows};skeletons={};selected={}
with zipfile.ZipFile(book) as source:
    for name in ('xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml'):
        saved={};root=None;data=None
        with source.open(name) as stream:
            for event,element in ET.iterparse(stream,events=('start','end')):
                if event=='start':
                    if root is None:root=element
                    if element.tag==M+'sheetData':data=element
                    continue
                if element.tag==M+'row':
                    row=int(element.get('r'))
                    if row in required:saved[row]=copy.deepcopy(element)
                    element.clear();data.remove(element)
        assert set(saved)==required
        skeletons[name]=root;selected[name]=saved
    packages=[]
    for label,rows in ranges.items():
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as crop:
            for info in source.infolist():
                if info.filename not in skeletons:crop.writestr(copy.copy(info),source.read(info.filename))
            for name,skeleton in skeletons.items():
                root=copy.deepcopy(skeleton);root.find(M+'dimension').set('ref','A1:V'+str(len(rows)+1));data=root.find(M+'sheetData')
                for new_row,old_row in enumerate([1]+rows,1):
                    row=copy.deepcopy(selected[name][old_row]);row.set('r',str(new_row))
                    for cell in row:
                        old_address=cell.get('r');letters=''.join(c for c in old_address if c.isalpha());cell.set('r',letters+str(new_row))
                    data.append(row)
                    restored=copy.deepcopy(row);restored.set('r',str(old_row))
                    for cell in restored:
                        letters=''.join(c for c in cell.get('r') if c.isalpha());cell.set('r',letters+str(old_row))
                    assert ET.tostring(restored)==ET.tostring(selected[name][old_row])
                crop.writestr(name,ET.tostring(root,encoding='utf-8',xml_declaration=True))
        packages.append({'label':label,'source_rows':[1]+rows,'render_range':'A1:V'+str(len(rows)+1),
            'projection_rows':list(range(1,len(rows)+2)),'base64':base64.b64encode(buffer.getvalue()).decode('ascii')})
print(json.dumps({'scope':'Read-only first/last projections extracted from the actual cropped XLSX XML; not a full-workbook engine import','packages':packages}))
`;

async function fromValidatedHistory(args, root, input, metadata, output, template, auditOutput, temp) {
  const started = performance.now(), reportPath = path.join(temp, 'q2_submission_history_report.json');
  const report = {status:'started',operation_id:OPERATION_ID,authoring_route:'crop_validated_history_XML_rows',
    output,output_start_s:1,output_end_s:OUTPUT_END_S,scope_sha256:SCOPE_SHA,
    exporter_sha256:await hashFile(fileURLToPath(import.meta.url)),previews:[],memory_samples:[],projection_mappings:[],projection_checks:[]};
  const memory = label => {
    const sample={label,...process.memoryUsage()};report.memory_samples.push(sample);
    insist(!args.rssLimitMiB || sample.rss<=args.rssLimitMiB*1048576,`RSS limit exceeded at ${label}`);
  };
  try {
    insist(args['failure-evidence'] && args['marker-receipt'] && args['interchange-manifest'], 'History mode requires explicit failure, marker and interchange evidence.');
    const failurePath=path.resolve(args['failure-evidence']),receiptPath=path.resolve(args['marker-receipt']),manifestPath=path.resolve(args['interchange-manifest']);
    insist(await hashFile(failurePath)===HISTORY_FAILURE_SHA,'Actual export failure evidence changed.');
    const failure=JSON.parse(await fs.readFile(failurePath,'utf8'));
    insist(failure.status==='fail' && failure.operation_id===OPERATION_ID && failure.output_end_s===OUTPUT_END_S && failure.scope_sha256===SCOPE_SHA && failure.exporter_sha256===HISTORY_FAILURE_EXPORTER_SHA && samePath(failure.output,output),'Failure provenance mismatch.');
    const exceeded=failure.memory_samples.find(s=>s.label==='after_export_before_save');
    insist(exceeded?.rss===3603632128 && failure.rss_limit_mib===2800 && failure.error.includes('RSS limit exceeded at after_export_before_save'),'The authorized export-capacity exception is not evidenced.');
    const receipt=JSON.parse(await fs.readFile(receiptPath,'utf8'));
    insist(receipt.status==='success' && receipt.operation_id===OPERATION_ID && receipt.output_end_s===OUTPUT_END_S && samePath(receipt.output,output),'Existing operation marker mismatch.');
    report.operation_marker={status:'reused_without_new_marker',receipt:receiptPath,sha256:await hashFile(receiptPath)};
    const manifest=JSON.parse(await fs.readFile(manifestPath,'utf8'));
    insist(JSON.stringify(manifest)===JSON.stringify(failure.input_manifest),'Interchange manifest differs from actual authoring attempt.');
    insist(samePath(manifest.input_npz,input) && samePath(manifest.metadata,metadata) && manifest.input_npz_sha256===INPUT_SHA && manifest.metadata_sha256===METADATA_SHA,'Wrong accepted source binding.');
    insist(await hashFile(input)===INPUT_SHA && await hashFile(metadata)===METADATA_SHA,'Accepted source changed.');
    report.input_manifest=manifest;report.interchange_manifest_sha256=await hashFile(manifestPath);
    report.failure_evidence={path:failurePath,sha256:HISTORY_FAILURE_SHA,status:failure.status,error:failure.error,
      actual_failed_exporter_sha256:failure.exporter_sha256,operation_id:failure.operation_id,elapsed_s:failure.elapsed_s,
      rss_limit_mib:failure.rss_limit_mib,observed_rss_bytes:exceeded.rss,failed_stage:exceeded.label,
      all_memory_samples:failure.memory_samples,previews_generated_before_failure:failure.previews.length,
      saved_new_workbook:false,scope:'Complete XLSX export exceeded the actual 2800 MiB process budget; full authoring and small native preview capability remained available.'};
    const history=path.join(root,'output/Q2/history');
    const prior=[{role:'workbook',current:output,archived:path.join(history,'result2_full_process_20260911.xlsx'),sha256:PRIOR_WORKBOOK_SHA},
      {role:'audit',current:auditOutput,archived:path.join(history,'workbook_audit_full_process_20260911.json'),sha256:PRIOR_AUDIT_SHA}];
    for (const item of prior) {
      insist(await hashFile(item.current)===item.sha256,`Prior official ${item.role} changed.`);
      insist(await hashFile(item.archived)===item.sha256,`Validated history ${item.role} changed.`);
    }
    const historicalAudit=JSON.parse(await fs.readFile(prior[1].archived,'utf8'));
    insist(historicalAudit.status==='pass' && historicalAudit.data_status==='pass' && historicalAudit.independent_xml.status==='pass' && historicalAudit.independent_xml.xlsx_sha256===PRIOR_WORKBOOK_SHA && historicalAudit.independent_xml.result_values_checked===8690934 && historicalAudit.input_npz_sha256===INPUT_SHA && historicalAudit.metadata_sha256===METADATA_SHA && historicalAudit.template_sha256===TEMPLATE_SHA,'History validation binding mismatch.');
    report.superseded_delivery={reason:'User clarified Q2 submission covers only the first three hours.',files:prior,retained_bytes_unchanged:true,
      historical_authoring_route:historicalAudit.authoring_route,historical_generator_sha256:historicalAudit.exporter_sha256};
    report.independent_interchange=JSON.parse(await run(PYTHON,['-B','-c',VERIFY_INTERCHANGE,manifestPath]));
    insist(report.independent_interchange.status==='pass' && report.independent_interchange.values_compared===453600,'Incomplete independent NPZ/interchange check.');
    memory('before_history_crop');
    const stagedWorkbook=path.join(temp,'result2.xlsx');
    // The original operation is already marked; no marker call occurs in this mode.
    report.history_crop=JSON.parse(await run(PYTHON,['-B','-c',CROP_HISTORY,prior[0].archived,stagedWorkbook,String(OUTPUT_END_S)]));
    insist(report.history_crop.status==='pass' && report.history_crop.source_sha256===PRIOR_WORKBOOK_SHA && report.history_crop.unchanged_member_count===10,'History crop preservation check failed.');
    report.independent_xml=JSON.parse(await run(PYTHON,['-B','-c',AUDIT,manifestPath,stagedWorkbook]));
    insist(report.independent_xml.status==='pass' && report.independent_xml.result_values_checked===453600 && report.independent_xml.xlsx_sha256===report.history_crop.sha256,'Full revised XML audit failed.');
    const projection=JSON.parse(await run(PYTHON,['-B','-c',HISTORY_PROJECTIONS,stagedWorkbook,String(OUTPUT_END_S)]));
    report.native_render_scope=projection.scope;
    const {SpreadsheetFile}=await loadTool(temp);
    for (const part of projection.packages) {
      const bytes=Buffer.from(part.base64,'base64');
      const workbook=await SpreadsheetFile.importXlsx(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
      report.projection_mappings.push({label:part.label,source_rows:part.source_rows,projection_rows:part.projection_rows,range:part.render_range});
      for (const {name,slug} of SHEETS) {
        const inspected=await workbook.inspect({kind:'table',sheetId:name,range:part.render_range,include:'values,formulas',tableMaxRows:9,tableMaxCols:22,maxChars:7000});
        report.projection_checks.push({sheet:name,label:part.label,ndjson:inspected.ndjson});
        report.previews.push(await render(workbook,name,part.render_range,path.join(temp,`${slug}_${part.label}.png`)));
        memory(`native_projection:${slug}:${part.label}`);
      }
    }
    insist(report.previews.length===4,'Four final-XML projections required.');
    insist(await hashFile(template)===TEMPLATE_SHA && await hashFile(path.join(root,'planning/Q2/output_scope_revision.md'))===SCOPE_SHA,'Template/scope changed.');
    insist(await hashFile(fileURLToPath(import.meta.url))===report.exporter_sha256 && await hashFile(failurePath)===HISTORY_FAILURE_SHA && await hashFile(receiptPath)===report.operation_marker.sha256,'Recovery source/evidence changed.');
    insist(await hashFile(stagedWorkbook)===report.independent_xml.xlsx_sha256,'Audited revised workbook changed.');
    for (const item of prior) {
      insist(await hashFile(item.current)===item.sha256,`Prior ${item.role} changed before commit.`);
      insist(await hashFile(item.archived)===item.sha256,`History ${item.role} changed before commit.`);
    }
    const placementStage=path.join(path.dirname(output),'.result2.xlsx.staging');
    await fs.copyFile(stagedWorkbook,placementStage,fsConstants.COPYFILE_EXCL);
    insist(await hashFile(placementStage)===report.independent_xml.xlsx_sha256,'Destination staging hash mismatch.');
    await fs.rename(placementStage,output);
    insist(await hashFile(output)===report.independent_xml.xlsx_sha256,'Revised workbook commit identity mismatch.');
    report.status='data_pass_visual_pending';report.elapsed_s=(performance.now()-started)/1000;
    const audit={schema:'q2_submission_workbook_audit_v1',status:'awaiting_visual_review',data_status:'pass',
      output,template,input_npz:input,metadata,input_npz_sha256:INPUT_SHA,metadata_sha256:METADATA_SHA,
      template_sha256:TEMPLATE_SHA,exporter_sha256:report.exporter_sha256,operation_id:OPERATION_ID,
      authoring_route:report.authoring_route,operation_marker:report.operation_marker,
      output_start_s:1,output_end_s:OUTPUT_END_S,scope_sha256:SCOPE_SHA,data_rows_per_sheet:OUTPUT_END_S,
      units:{time:'s',radius:'cm',temperature:'°C',moisture:'kg water/kg dry solid'},
      rounding:'Original validated numeric XML values and 0.0000 styles preserved; independently compared with Decimal.from_float(binary64) rounded to 0.0001, ties away from zero.',
      output_scope:manifest.output_scope,superseded_delivery:report.superseded_delivery,
      capability:'Recovery from the observed full-XLSX export memory failure uses bounded history-row cropping. Available artifact-tool import/inspect/render is used only on exact final-XML projections.',
      fallback_failure_evidence:report.failure_evidence,interchange_manifest_sha256:report.interchange_manifest_sha256,
      independent_interchange:report.independent_interchange,history_crop:report.history_crop,independent_xml:report.independent_xml,
      native_render_scope:report.native_render_scope,native_previews:report.previews,memory_samples:report.memory_samples,elapsed_s:report.elapsed_s,
      visual_review:{status:'pending',scope:report.native_render_scope,mappings:report.projection_mappings,note:'Four native first/last projections rendered; actual human/agent image inspection remains required.'},
      detailed_export_report:reportPath};
    const auditStage=path.join(path.dirname(auditOutput),'.workbook_audit.json.staging');
    await fs.writeFile(auditStage,JSON.stringify(audit,null,2),{flag:'wx'});await fs.rename(auditStage,auditOutput);
    await fs.writeFile(reportPath,JSON.stringify(report,null,2));
    console.log(JSON.stringify({status:report.status,output,audit:auditOutput,report:reportPath,values_checked:453600,sha256:report.independent_xml.xlsx_sha256}));
  } catch (e) {
    report.status='fail';report.error=e.stack||String(e);report.elapsed_s=(performance.now()-started)/1000;
    await fs.writeFile(reportPath,JSON.stringify(report,null,2));throw e;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args) {
    console.log('node export_submission.mjs --input <NPZ> --metadata <source JSON> --output output/Q2/result2.xlsx --template 附件/附件3/result2.xlsx [--project-root <project>] [--preview-dir <TEMP child>] [--chunk-rows 1024] [--rss-limit-mib 0] [--from-validated-history --failure-evidence <prior report> --marker-receipt <existing receipt> --interchange-manifest <prior manifest>]');
    return;
  }
  const root = path.resolve(args['project-root'] ?? PROJECT_ROOT);
  const input = path.resolve(root, args.input), metadata = path.resolve(root, args.metadata);
  const output = path.resolve(root, args.output), template = path.resolve(root, args.template);
  const auditOutput = path.join(root, 'output/Q2/workbook_audit.json');
  insist(samePath(output, path.join(root, 'output/Q2/result2.xlsx')), 'Only the admitted Q2 result2.xlsx output is allowed.');
  insist(samePath(template, path.join(root, '附件/附件3/result2.xlsx')), 'Use the original Q2 template.');
  insist(await hashFile(template) === TEMPLATE_SHA, 'Official template identity mismatch.');
  insist(await hashFile(path.join(root, 'planning/Q2/output_scope_revision.md')) === SCOPE_SHA, 'Q2 output scope identity mismatch.');
  const temp = args['preview-dir'] ? path.resolve(args['preview-dir']) : path.join(os.tmpdir(), 'cumcm-q2-workbook-3h');
  const relative = path.relative(os.tmpdir(), temp);
  insist(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Preview/interchange directory must be inside TEMP.');
  await fs.mkdir(temp, { recursive: true });
  if (args.fromValidatedHistory) return fromValidatedHistory(args, root, input, metadata, output, template, auditOutput, temp);
  const reportPath = path.join(temp, 'q2_submission_export_report.json');
  const started = performance.now();
  const report = { status: 'started', operation_id: OPERATION_ID, output_start_s: 1, output_end_s: OUTPUT_END_S, scope_sha256: SCOPE_SHA, input, metadata, output, audit_output: auditOutput, template, preview_dir: temp, template_sha256: TEMPLATE_SHA,
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
    insist(await hashFile(input) === INPUT_SHA && await hashFile(metadata) === METADATA_SHA, 'Accepted source identity mismatch.');
    const history = path.join(root, 'output/Q2/history');
    const prior = [
      { role: 'workbook', current: output, archived: path.join(history, 'result2_full_process_20260911.xlsx'), sha256: PRIOR_WORKBOOK_SHA },
      { role: 'audit', current: auditOutput, archived: path.join(history, 'workbook_audit_full_process_20260911.json'), sha256: PRIOR_AUDIT_SHA },
    ];
    for (const item of prior) insist(await hashFile(item.current) === item.sha256, `Prior official ${item.role} identity mismatch; no replacement authorized for different bytes.`);
    await fs.mkdir(history, { recursive: true });
    for (const item of prior) {
      try { await fs.copyFile(item.current, item.archived, fsConstants.COPYFILE_EXCL); }
      catch (e) { if (e.code !== 'EEXIST') throw e; }
      insist(await hashFile(item.archived) === item.sha256, `Archived ${item.role} identity mismatch.`);
    }
    report.superseded_delivery = { reason: 'User clarified Q2 submission covers only the first three hours.', files: prior, retained_bytes_unchanged: true };
    const manifest = JSON.parse(await run(PYTHON, ['-B', '-c', PREPARE, input, metadata, temp, String(args.chunkRows)]));
    insist(manifest.output_end_s === OUTPUT_END_S && manifest.row_count === OUTPUT_END_S, 'Wrong submission range.');
    report.input_manifest = manifest;
    const { FileBlob, SpreadsheetFile } = await loadTool(temp);
    const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
    report.template_inspection = (await workbook.inspect({ kind: 'sheet', include: 'id,name', maxChars: 2000 })).ndjson;
    // The unchanged original template was already rendered and visually reviewed.
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
        for (let first = 0; first < manifest.output_end_s; first += args.chunkRows) {
          const rows = Math.min(args.chunkRows, manifest.output_end_s - first);
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
          if (first === 0 || first + rows === manifest.output_end_s || Math.floor(first / args.chunkRows) % 4 === 0) {
            memory(`${field}:${first + rows}/${manifest.output_end_s}`);
            console.log(JSON.stringify({ progress: field, rows_written: first + rows, total_rows: manifest.output_end_s, rss_mib: Math.round(process.memoryUsage().rss / 1048576) }));
          }
        }
      } finally { await source.close(); }
      sheet.freezePanes.freezeRows(1); sheet.freezePanes.freezeColumns(1);
    }
    workbook.recalculate();
    report.inspections = [];
    const last = manifest.output_end_s + 1;
    const ranges = [['first', 'A1:V8'], ['last', `A${last - 7}:V${last}`]];
    for (const { name, slug } of SHEETS) {
      for (const [label, range] of ranges) {
        report.inspections.push({ sheet: name, label, range, ndjson: (await workbook.inspect({ kind: 'table', sheetId: name, range, include: 'values,formulas', tableMaxRows: 8, tableMaxCols: 22, maxChars: 7000 })).ndjson });
        report.previews.push(await render(workbook, name, range, path.join(temp, `${slug}_${label}.png`)));
        memory(`native_render:${slug}:${label}`);
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
    insist(report.independent_xml.result_values_checked === manifest.output_end_s * 42, 'Incomplete full XML coverage.');
    insist(await hashFile(template) === TEMPLATE_SHA, 'Original template changed.');
    for (const item of prior) {
      insist(await hashFile(item.current) === item.sha256, `Prior ${item.role} changed during authoring.`);
      insist(await hashFile(item.archived) === item.sha256, `Archived ${item.role} changed during authoring.`);
    }
    const placementStage = path.join(path.dirname(output), '.result2.xlsx.staging');
    await fs.copyFile(stagedWorkbook, placementStage, fsConstants.COPYFILE_EXCL);
    insist(await hashFile(placementStage) === report.independent_xml.xlsx_sha256, 'Destination-side staging hash mismatch.');
    // Both paths are on the output volume. Preserve the validated TEMP file on failure.
    await fs.rename(placementStage, output);
    insist(await hashFile(output) === report.independent_xml.xlsx_sha256, 'Workbook changed during final placement.');
    report.status = 'pass';
    report.elapsed_s = (performance.now() - started) / 1000;
    report.visual_review = 'Four first/last native ranges of the complete artifact-tool authoring workbook were rendered. Actual image review remains required.';
    report.native_render_scope = 'Full 10800-row-per-sheet artifact-tool authoring workbook, before export; saved XLSX independently checked in full by XML. No XML projections used.';
    const audit = {
      schema: 'q2_submission_workbook_audit_v1', status: 'awaiting_visual_review', data_status: 'pass',
      output, template, input_npz: input, metadata,
      input_npz_sha256: manifest.input_npz_sha256, metadata_sha256: manifest.metadata_sha256,
      template_sha256: TEMPLATE_SHA, exporter_sha256: report.exporter_sha256,
      operation_id: OPERATION_ID, output_start_s: 1, output_end_s: OUTPUT_END_S, scope_sha256: SCOPE_SHA,
      data_rows_per_sheet: OUTPUT_END_S, units: report.units, rounding: report.rounding,
      output_scope: manifest.output_scope, superseded_delivery: report.superseded_delivery,
      capability: 'Normal artifact-tool complete authoring and export for the revised three-hour range; no large-table fallback used.',
      native_render_scope: report.native_render_scope, memory_samples: report.memory_samples, elapsed_s: report.elapsed_s,
      independent_xml: report.independent_xml, native_previews: report.previews,
      visual_review: { status: 'pending', note: report.visual_review },
      detailed_export_report: reportPath,
    };
    const auditStage = path.join(path.dirname(auditOutput), '.workbook_audit.json.staging');
    await fs.writeFile(auditStage, JSON.stringify(audit, null, 2), { flag: 'wx' });
    await fs.rename(auditStage, auditOutput);
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ status: report.status, output, audit: auditOutput, report: reportPath, output_end_s: OUTPUT_END_S, values_checked: manifest.output_end_s * 42, sha256: report.independent_xml.xlsx_sha256 }));
  } catch (e) {
    report.status = 'fail'; report.error = e.stack || String(e); report.elapsed_s = (performance.now() - started) / 1000;
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
    throw e;
  }
}

main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
