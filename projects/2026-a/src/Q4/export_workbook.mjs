/** Q4: official moving-domain moisture workbook from the actual validated Q4 NPZ.
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
const TEMPLATE_SHA = '86e9300ffa3d30c43de895ea6723da943e85b8740b137bcae5af7107f076eeac';
const OPERATION_ID = 'q4-result4';
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
  const a = { verification: [] };
  const allowed = new Set(['project-root', 'input', 'metadata', 'template', 'output', 'spec', 'preview-dir', 'template-reviewed-sha', 'rss-limit-mib']);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--preview-template') { insist(!a.previewTemplate, 'Repeated mode'); a.previewTemplate = true; continue; }
    if (argv[i] === '--help') return null;
    if (argv[i] === '--verification') { insist(argv[i + 1] && !argv[i + 1].startsWith('--'), 'Missing verification path'); a.verification.push(argv[++i]); continue; }
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

// Numerical interchange only. This reader does not create or edit a workbook.
const PREPARE = String.raw`
import sys,json,hashlib
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
import numpy as np
source,metadata,geometry,dest=map(Path,sys.argv[1:5])
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def rounded(v):return format(Decimal.from_float(float(v)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP),'.4f')
meta=json.loads(metadata.read_text(encoding='utf-8-sig'));g=json.loads(geometry.read_text(encoding='utf-8-sig'))
assert meta['question']=='Q4' and meta['case_role']=='main' and meta['success'] is True
assert meta['drying_complete'] is True and meta['comparison_complete'] is True
assert meta['properties']=='appendix4' and meta['scenario']=='mean_tail' and meta['radius']['method']=='linear'
assert type(meta['grid_n']) is int and meta['grid_n']>=20 and meta['grid_n']%20==0 and meta['tight'] is False
assert meta['method']=='material_coordinate_nodal_finite_volume_segmented_BDF'
assert meta['result_sha256']==digest(source) and meta['radius_json_sha256']==digest(geometry)
end=meta['n_end'];assert type(end) is int and end>0 and meta['threshold_kg_kg']==.15
times=sorted(set(range(60,end+1,60))|{end});table_times=sorted(set(range(21600,end+1,21600))|{end})
assert len(times)<=1048575
positions=[0,5,10,15,20]
with np.load(source,allow_pickle=False) as z:
    t,r,mask=z['time_s'],z['radius_m'],z['inside_mask'];c=z['moisture_kg_kg'];s=z['surface_moisture_kg_kg'];rad=z['surface_radius_m']
    assert t.ndim==1 and t.dtype==np.dtype('int64') and t[0]==0 and np.all(np.diff(t)>0)
    assert np.array_equal(t,np.array(sorted(set(range(0,meta['common_end_s']+1,60))|{end,meta['common_end_s']}),dtype=np.int64))
    assert r.shape==(21,) and np.allclose(r,np.arange(21)*.001,rtol=0,atol=1e-15)
    assert c.shape==mask.shape==(len(t),21) and c.dtype==np.dtype('float64') and mask.dtype==np.dtype('bool')
    assert s.shape==rad.shape==(len(t),) and np.isfinite(s).all() and np.all(s>0) and np.isfinite(rad).all() and np.all(rad>0)
    assert np.isfinite(c[mask]).all() and np.all(c[mask]>0) and np.isnan(c[~mask]).all()
    expected_mask=r[None,:]<=rad[:,None]+16*np.finfo(float).eps*np.maximum(.02,rad[:,None])
    assert np.array_equal(mask,expected_mask)
    official=(t>0)&(t<=end)&((t%60==0)|(t==end))
    assert z['official_output_mask'].dtype==np.dtype('bool') and np.array_equal(z['official_output_mask'],official)
    assert t[official].tolist()==times
    indexes=np.searchsorted(t,times);table_indexes=np.searchsorted(t,table_times)
    assert np.array_equal(t[indexes],times) and np.array_equal(t[table_indexes],table_times)
    matrix=np.c_[c[indexes],s[indexes]].astype('<f8')
    binary=dest/'moisture_and_surface.f64le';binary.write_bytes(matrix.tobytes(order='C'))
    inside=int(mask[indexes].sum());outside=int((~mask[indexes]).sum())
    table_raw=[];table_display=[]
    for index in table_indexes:
        row=[float(c[index,p]) if mask[index,p] else None for p in positions]+[float(s[index])]
        table_raw.append(row);table_display.append([rounded(v) if v is not None else None for v in row])
    summary={'schema_version':'1.0','question':'Q4','input_npz':str(source),'input_npz_sha256':digest(source),
      'metadata':str(metadata),'metadata_sha256':digest(metadata),'radius_json_sha256':digest(geometry),
      'original_run_spec_sha256':meta['spec_sha256'],'n_end_s':end,'t_cross_s':meta['t_cross_s'],
      'display_end_h':rounded(end/3600),'threshold_kg_kg':.15,
      'endpoint_check_source':meta['endpoint_check'],
      'table6':{'table_number':6,'time_s':table_times,'time_h':[v/3600 for v in table_times],
        'display_time_h':[rounded(v/3600) for v in table_times],
        'row_roles':['actual_terminal_second' if v==end else str(v//3600)+'h' for v in table_times],
        'fixed_radius_m':r[positions].tolist(),'fixed_radius_cm':[0,.5,1,1.5,2],
        'column_roles':['fixed_physical_radius']*5+['actual_moving_surface'],
        'inside_mask':mask[np.ix_(table_indexes,positions)].tolist(),
        'surface_radius_m':rad[table_indexes].tolist(),'values':table_raw,'display_4dp':table_display,
        'units':'kg water/kg dry solid','outside_domain':'JSON null corresponds to a genuinely empty workbook cell, not zero or a missing measurement.'},
      'workbook_sampling':{'time_s':times,'fixed_radius_m':r.tolist(),'fixed_radius_cm':[j/10 for j in range(21)],
        'surface_radius_m':rad[indexes].tolist(),'data_rows':len(times),'columns':23,
        'schedule':'Positive multiples of 60 seconds through the actual strict endpoint, plus that endpoint exactly once.',
        'final_interval_s':times[-1]-times[-2] if len(times)>1 else times[-1]}}
    manifest={'schema':'q4_workbook_f64_v1','input_npz':str(source),'input_npz_sha256':digest(source),
      'metadata':str(metadata),'metadata_sha256':digest(metadata),'radius_json_sha256':digest(geometry),
      'terminal_time_s':end,'time_s':times,'radius_m':r.tolist(),'surface_radius_m':rad[indexes].tolist(),
      'data_rows':len(times),'columns':23,'valid_fixed_values':inside,'outside_blank_cells':outside,
      'surface_values':len(times),'total_numeric_field_values':inside+len(times),
      'field':{'path':str(binary),'sha256':digest(binary),'dtype':'<f8','shape':[len(times),22]},
      'table6_rows':len(table_times),'sampling':summary['workbook_sampling']['schedule']}
(dest/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
(dest/'summary_values.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,allow_nan=False))
`;
// Independent read of original NPZ and saved XML. Writer/interchange values are
// never used as an audit oracle. Outside-domain NaNs must become genuine blanks.
const AUDIT = String.raw`
import sys,json,zipfile,hashlib,math,posixpath
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP,localcontext
import xml.etree.ElementTree as ET
import numpy as np
book,source,metadata,geometry,summary_path=map(Path,sys.argv[1:6])
M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';RID='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
errors=[];error_count=0;numeric_count=0;format_count=0;blank_count=0;surface_count=0;fixed_count=0
maximum_saved=0.;maximum_rounding=0.;row_count=0;actual_cell_count=0;formula_count=0
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
def sample_index(axis,t):
    i=int(np.searchsorted(axis,t));assert i<len(axis) and axis[i]==t,'Required exact sample missing';return i
meta=json.loads(metadata.read_text(encoding='utf-8-sig'));g=json.loads(geometry.read_text(encoding='utf-8-sig'))
summary=json.loads(summary_path.read_text(encoding='utf-8'));table=summary['table6']
end=meta['n_end'];assert type(end) is int and end>0
times=sorted(set(range(60,end+1,60))|{end});table_times=sorted(set(range(21600,end+1,21600))|{end});positions=[0,5,10,15,20]
with np.load(source,allow_pickle=False) as z:
    t,r,c,mask=z['time_s'],z['radius_m'],z['moisture_kg_kg'],z['inside_mask']
    rad,s=z['surface_radius_m'],z['surface_moisture_kg_kg'];xi=z['mesh_xi'];n=meta['grid_n']
    check(meta['success'] is True and meta['drying_complete'] is True and meta['comparison_complete'] is True,'Complete accepted source run')
    check(meta['question']=='Q4' and meta['case_role']=='main' and meta['properties']=='appendix4' and meta['scenario']=='mean_tail' and meta['radius']['method']=='linear','Official main-model scenario')
    check(type(n) is int and n>=20 and n%20==0 and meta['tight'] is False and meta['method']=='material_coordinate_nodal_finite_volume_segmented_BDF','Ordinary main grid/tight/method contract')
    check(meta['result_sha256']==digest(source) and meta['radius_json_sha256']==digest(geometry),'Source metadata result/geometry identity')
    check(summary['input_npz_sha256']==digest(source) and summary['metadata_sha256']==digest(metadata) and summary['radius_json_sha256']==digest(geometry),'Summary source bindings')
    check(summary['original_run_spec_sha256']==meta['spec_sha256'] and summary['specification']['sha256']==meta['spec_sha256'],'Summary agrees with actual model specification')
    check(t.dtype==np.dtype('int64') and t.ndim==1 and np.array_equal(t,np.array(sorted(set(range(0,meta['common_end_s']+1,60))|{end,meta['common_end_s']}),dtype=np.int64)),'Complete unique minute/endpoint/common time axis')
    check(r.shape==(21,) and np.allclose(r,np.arange(21)*.001,rtol=0,atol=1e-15),'Fixed physical radii 0..0.02 m')
    check(xi.shape==(n+1,) and np.allclose(xi,np.linspace(0,1,n+1),rtol=0,atol=1e-15),'Material mesh axis')
    check(c.dtype==np.dtype('float64') and c.shape==(len(t),21) and mask.dtype==np.dtype('bool') and mask.shape==c.shape,'Fixed field and boolean domain mask shapes')
    check(rad.shape==s.shape==t.shape and np.isfinite(rad).all() and np.all(rad>0) and np.isfinite(s).all() and np.all(s>0),'Actual surface series')
    node_t=np.array([v['time_s'] for v in g['nodes']],dtype=float);node_r=np.array([v['radius_cm'] for v in g['nodes']],dtype=float)
    check(g['units']=={'time_s':'s','radius_cm':'cm','evaluate_radius':'m'} and g['interpolation']=='linear','Geometry units and primary interpolation')
    if t[-1]>node_t[-1]:check(meta['radius']['continuation']=='hold_last' and meta['radius']['continuation_used'] is True,'Explicit radius continuation beyond observations')
    else:check(meta['radius']['continuation_used'] is False,'No unused radius extrapolation claimed')
    wanted_r=np.interp(t,node_t,node_r)*.01
    check(np.allclose(rad,wanted_r,rtol=0,atol=2e-17),'Every sample radius independently interpolated from frozen geometry')
    wanted_mask=r[None,:]<=rad[:,None]+16*np.finfo(float).eps*np.maximum(.02,rad[:,None])
    check(np.array_equal(mask,wanted_mask),'Every inside/outside classification uses only machine-equality tolerance')
    check(np.isfinite(c[mask]).all() and np.all(c[mask]>0) and np.isnan(c[~mask]).all(),'Inside finite positive; outside source NaN')
    thermal=z['temperature_C'];check(thermal.shape==c.shape and np.isfinite(thermal[mask]).all() and np.isnan(thermal[~mask]).all(),'Companion thermal field domain consistency')
    official=(t>0)&(t<=end)&((t%60==0)|(t==end))
    check(z['official_output_mask'].dtype==np.dtype('bool') and np.array_equal(z['official_output_mask'],official),'Entire official output mask and endpoint deduplication')
    indices=[sample_index(t,v) for v in times];check(t[official].tolist()==times,'Exact workbook time schedule')
    snap_t=z['snapshot_time_s'];snap_r=z['snapshot_radius_m'];snap_c=z['moisture_snapshots']
    check(snap_c.shape==(len(snap_t),n+1) and snap_r.shape==snap_t.shape and np.isfinite(snap_c).all(),'All full-node moisture snapshots')
    maxima=z['max_moisture_kg_kg'];arg=z['max_moisture_node'];max_r=z['max_moisture_radius_m']
    check(maxima.shape==arg.shape==max_r.shape==t.shape and np.isfinite(maxima).all(),'Stored all-node maximum axes')
    check(np.all(arg>=0) and np.all(arg<=n) and np.allclose(max_r,rad*xi[arg],rtol=0,atol=1e-15),'Whole-node maximum physical radius identity')
    check(np.all(np.nanmax(c,axis=1)<=maxima+1e-12) and np.all(s<=maxima+1e-12),'Output fixed/surface values do not exceed all-node maximum')
    terminal={};snapshot_checks=[]
    for role,instant in [('before_n_end',end-1),('n_end',end)]:
        index=meta['snapshot_roles'][role];values=snap_c[index];radius=float(snap_r[index]);maximum=float(values.max());argmax=int(values.argmax())
        check(snap_t[index]==instant and abs(radius-float(np.interp(instant,node_t,node_r)*.01))<=2e-17,'Exact terminal snapshot time/radius '+role)
        check(maximum>=.15 if role=='before_n_end' else maximum<.15,'Unrounded strict adjacent-second endpoint '+role)
        key='before' if role=='before_n_end' else 'end';published=meta['endpoint_check']
        check(published[key+'_time_s']==instant and published[key+'_max_moisture_kg_kg']==maximum and published[key+'_max_node']==argmax and abs(published[key+'_max_radius_m']-radius*xi[argmax])<=1e-15,'Metadata terminal check '+role)
        terminal[role]={'time_s':instant,'maximum_kg_kg':maximum,'argmax_node':argmax,'argmax_radius_m':float(radius*xi[argmax]),'nodes_compared':n+1,'strictly_below_threshold':bool(maximum<.15)}
    event_index=meta['snapshot_roles']['threshold_crossing']
    check(end-1<=meta['t_cross_s']<=end and snap_t[event_index]==meta['t_cross_s'] and abs(float(snap_c[event_index].max())-.15)<=5e-9,'Stored continuous crossing and adjacent-second bracket')
    last_idx=sample_index(t,end)
    check(maxima[last_idx]==terminal['n_end']['maximum_kg_kg'],'Ending sample maximum agrees with every-node snapshot')
    check(np.all(maxima[t>=end]<.15),'No observed later maximum returns to threshold')
    check(summary['n_end_s']==end and summary['t_cross_s']==meta['t_cross_s'] and summary['display_end_h']==format(rounded(end/3600),'.4f') and summary['threshold_kg_kg']==.15,'Summary endpoint semantics')
    check(summary['endpoint_check_source']==meta['endpoint_check'],'Summary preserves actual endpoint metadata')
    check(table['time_s']==table_times and table['fixed_radius_m']==r[positions].tolist() and table['fixed_radius_cm']==[0,.5,1,1.5,2] and table['column_roles']==['fixed_physical_radius']*5+['actual_moving_surface'],'Table6 fixed/surface axes')
    check(summary['workbook_sampling']['time_s']==times and summary['workbook_sampling']['fixed_radius_m']==r.tolist(),'Summary complete workbook axes')
    check(summary['workbook_sampling']['surface_radius_m']==rad[indices].tolist() and summary['workbook_sampling']['data_rows']==len(times) and summary['workbook_sampling']['columns']==23,'Summary every actual surface radius and workbook shape')
    check(all(len(table[key])==len(table_times) for key in ['time_h','display_time_h','row_roles','inside_mask','surface_radius_m','values','display_4dp']),'Exact Table6 row coverage')
    check(all(len(row)==6 for row in table['values']) and all(len(row)==6 for row in table['display_4dp']) and all(len(row)==5 for row in table['inside_mask']),'Exact Table6 numeric/blank column coverage')
    table_checks=[];table_values=0;table_blanks=0
    for row,instant in enumerate(table_times):
        i=sample_index(t,instant);role='n_end' if instant==end else 'summary_'+str(instant)+'s';si=meta['snapshot_roles'][role]
        values=snap_c[si];radius=float(snap_r[si]);expected=mask[i,positions]
        check(snap_t[si]==instant and abs(radius-rad[i])<=2e-17,'Table6 exact full snapshot '+str(instant))
        check(table['inside_mask'][row]==expected.tolist() and table['surface_radius_m'][row]==float(rad[i]),'Table6 domain/surface radius '+str(instant))
        check(table['time_h'][row]==instant/3600 and table['display_time_h'][row]==format(rounded(instant/3600),'.4f'),'Table6 time display '+str(instant))
        for column in range(6):
            inside=column==5 or bool(expected[column]);want=float(s[i]) if column==5 else float(c[i,positions[column]]) if inside else None
            if inside:
                node_value=float(values[-1]) if column==5 else float(np.interp(min(float(r[positions[column]]/radius),1.),xi,values))
                check(abs(node_value-want)<=1e-12,'Table6 physical sample from full snapshot '+str((row,column)))
                display=format(rounded(want),'.4f');table_values+=1
            else:display=None;table_blanks+=1
            ok=table['values'][row][column]==want and table['display_4dp'][row][column]==display
            check(ok,'Table6 raw/display cell '+str((row,column)))
            table_checks.append({'time_s':instant,'column':column+1,'kind':'surface' if column==5 else 'fixed_radius','inside':inside,'raw':want,'display_4dp':display,'passed':ok})
        snapshot_checks.append({'time_s':instant,'snapshot_role':role,'nodes':n+1})
    with zipfile.ZipFile(book) as archive:
        strings=[''.join(v.text or '' for v in si.iter(M+'t')) for si in ET.fromstring(archive.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in archive.namelist() else []
        styles=ET.fromstring(archive.read('xl/styles.xml'));formats={f.get('numFmtId'):f.get('formatCode') for f in styles.findall(M+'numFmts/'+M+'numFmt')};xfs=styles.findall(M+'cellXfs/'+M+'xf')
        sheets=ET.fromstring(archive.read('xl/workbook.xml')).findall(M+'sheets/'+M+'sheet')
        check(len(sheets)==1 and sheets[0].get('name')=='Sheet1','Exactly original Sheet1')
        rels={v.get('Id'):v.get('Target') for v in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))};target=rels[sheets[0].get(RID)]
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        dimension=None;pane=None;hidden=0;merges=0;sheetdata=None
        with archive.open(target) as stream,localcontext() as context:
            context.prec=100
            for event,element in ET.iterparse(stream,events=('start','end')):
                if event=='start':
                    if element.tag==M+'sheetData':sheetdata=element
                    continue
                if element.tag==M+'dimension':dimension=element.get('ref')
                elif element.tag==M+'pane':pane=dict(element.attrib)
                elif element.tag==M+'mergeCell':merges+=1
                elif element.tag==M+'col':hidden+=element.get('hidden')=='1'
                elif element.tag==M+'row':
                    row_count+=1;row=int(element.get('r','0'));check(row==row_count and row<=len(times)+1,'Sequential exact output rows')
                    hidden+=element.get('hidden')=='1';cells=element.findall(M+'c');actual_cell_count+=len(cells)
                    addresses=[cell.get('r') for cell in cells];allowed=[chr(65+j)+str(row) for j in range(23)]
                    check(len(addresses)==len(set(addresses)) and set(addresses)<=set(allowed),'No duplicate/outside A:W cells')
                    mapped={cell.get('r'):cell for cell in cells}
                    for cell in cells:formula_count+=cell.find(M+'f') is not None
                    if row>len(times)+1:element.clear();sheetdata.remove(element);continue
                    for column,address in enumerate(allowed):
                        cell=mapped.get(address);node=cell.find(M+'v') if cell is not None else None;ctype=cell.get('t') if cell is not None else None
                        if ctype=='s' and node is not None:value=strings[int(node.text)]
                        elif ctype=='inlineStr':value=''.join(v.text or '' for v in cell.iter(M+'t'))
                        elif ctype=='str' and node is not None:value=node.text or ''
                        elif ctype in (None,'n') and node is not None:
                            try:value=float(node.text)
                            except (ValueError,TypeError):value=None
                        else:value=None
                        if row==1:
                            expected='时间\\到药材中心的距离' if column==0 else '药材表面' if column==22 else (column-1)/10
                            check(value==expected,'Header '+address);continue
                        i=indices[row-2]
                        if column==0:check(type(value) is float and value==times[row-2],'Integer second '+address);continue
                        inside=column==22 or bool(mask[i,column-1])
                        if not inside:
                            blank_count+=1
                            empty=cell is None or (ctype in (None,'n') and node is None and cell.find(M+'f') is None and cell.find(M+'is') is None)
                            check(empty,'Outside domain must be genuinely blank '+address);continue
                        want=float(s[i]) if column==22 else float(c[i,column-1]);numeric_count+=1
                        if column==22:surface_count+=1
                        else:fixed_count+=1
                        good=type(value) is float and math.isfinite(value);check(good,'Finite numeric inside/surface '+address)
                        if good:
                            expected=float(rounded(want));maximum_saved=max(maximum_saved,abs(value-expected));maximum_rounding=max(maximum_rounding,abs(value-want))
                            check(value==expected,'Independent binary64 four-decimal rounding '+address)
                        style=int(cell.get('s','0')) if cell is not None else -1;format_count+=1
                        check(0<=style<len(xfs) and formats.get(xfs[style].get('numFmtId'))=='0.0000','Numeric four-decimal format '+address)
                    element.clear();sheetdata.remove(element)
        expected_extent='A1:W'+str(len(times)+1)
        # SheetDimension is optional; exact rows, allowed addresses, every header,
        # every time cell and the mandatory W surface cell are checked above.
        check(row_count==len(times)+1,'Final workbook row extent from actual cells')
        check(dimension is None or dimension==expected_extent,'Optional declared dimension agrees with actual checked extent')
        check(pane is not None and pane.get('topLeftCell')=='B2' and pane.get('state')=='frozen','Frozen header/time panes')
        check(hidden==0 and merges==0 and formula_count==0,'No hidden data, merges, or formulas')
        check(fixed_count==int(mask[indices].sum()) and blank_count==int((~mask[indices]).sum()) and surface_count==len(times),'All valid, blank and actual surface cell coverage')
        check(numeric_count==format_count==fixed_count+surface_count,'Complete numeric format coverage')
check(meta['result_sha256']==digest(source),'Original NPZ unchanged after XML audit')
result={'status':'pass' if error_count==0 else 'fail','error_count':error_count,'errors':errors,
 'terminal_time_s':end,'data_rows':len(times),'sheet_rows':row_count,'columns':23,'dimension':dimension,
 'actual_extent_checked':'A1:W'+str(len(times)+1),'extent_source':'Sequential actual rows, unique allowed addresses, all headers and mandatory time/surface cells; optional dimension must agree when present.',
 'actual_serialized_cells':actual_cell_count,'logical_cells_checked':(len(times)+1)*23,
 'fixed_inside_values_checked':fixed_count,'outside_blank_cells_checked':blank_count,'surface_values_checked':surface_count,
 'result_values_checked':numeric_count,'numeric_formats_checked':format_count,
 'maximum_saved_vs_rounded_difference':maximum_saved,'maximum_absolute_export_rounding':maximum_rounding,
 'all_source_domain_samples_checked':int(mask.size),'surface_radius_samples_checked':len(t),
 'strict_endpoint':terminal,'endpoint_scope':'Adjacent integer full-node snapshots bracket the strict threshold and agree with stored crossing. This checks the retained numerical result, not a continuum stopping-time proof.',
 'table6':{'rows':len(table_times),'cells_checked':len(table_times)*6,'numeric_values_checked':table_values,'outside_blanks_checked':table_blanks,'checks':table_checks,'snapshot_cross_checks':snapshot_checks},
 'input_npz_sha256':digest(source),'metadata_sha256':digest(metadata),'radius_json_sha256':digest(geometry),
 'xlsx_sha256':digest(book),'xlsx_bytes':book.stat().st_size,'summary_sha256':digest(summary_path)}
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
`;
async function readBinding(state, root, p, {requireFrozen=false,checkRegistered=false}={}) {
  const key=path.relative(root,p).split(path.sep).join('/');
  insist(key && !key.startsWith('../') && !path.isAbsolute(key),'Evidence must stay in project');
  const identity=state.artifacts[key],sha256=await hashFile(p);
  if(requireFrozen)insist(identity?.identity_class==='frozen' && identity?.status==='validated' && identity?.sha256===sha256,`Actual frozen validated shared/spec input required: ${key}`);
  if(identity && (checkRegistered || identity.identity_class==='frozen'))insist(identity.sha256===sha256,`Already registered input identity mismatch: ${key}`);
  return {path:p,artifact_path:key,sha256,identity_class:identity?.identity_class??'not_registered',status:identity?.status??'not_registered'};
}
async function place(source,target,expected) {
  insist(await absent(target),`Existing official identity cannot be overwritten: ${target}`);
  const intermediate=path.join(path.dirname(target),'.'+path.basename(target)+'.staging');
  await fs.copyFile(source,intermediate,fsConstants.COPYFILE_EXCL);
  insist(await hashFile(intermediate)===expected,'Destination-side staging identity mismatch');
  await fs.rename(intermediate,target);
  insist(await hashFile(target)===expected,'Final placement identity mismatch');
}
async function main() {
  const args=argsOf(process.argv.slice(2));
  if(!args){console.log('node export_workbook.mjs --project-root <project> [--preview-template] --input <actual verified Q4 NPZ> --metadata <matching JSON> --verification <actual passing report> [--verification <additional report>] --template-reviewed-sha <reviewed template SHA> [--preview-dir <TEMP child>] [--rss-limit-mib 2800]');return;}
  const root=path.resolve(args['project-root']??ROOT);
  const template=path.resolve(root,args.template??'附件/附件3/result4.xlsx');
  const output=path.resolve(root,args.output??'output/Q4/result4.xlsx');
  const specification=path.resolve(root,args.spec??'planning/Q4/model_spec.md');
  const geometry=path.join(root,'output/GEOMETRY/q4_radius.json'),boundary=path.join(root,'output/ENV/q2_boundary.json');
  const auditOutput=path.join(root,'output/Q4/workbook_audit.json'),summaryOutput=path.join(root,'output/Q4/summary_values.json');
  const temp=path.resolve(args['preview-dir']??path.join(os.tmpdir(),'cumcm-q4-workbook'));
  const relative=path.relative(os.tmpdir(),temp);
  insist(relative && !relative.startsWith('..') && !path.isAbsolute(relative),'Previews/interchange must stay inside TEMP');
  insist(samePath(template,path.join(root,'附件/附件3/result4.xlsx')) && await hashFile(template)===TEMPLATE_SHA,'Actual original Q4 template identity mismatch');
  insist(samePath(output,path.join(root,'output/Q4/result4.xlsx')) && samePath(specification,path.join(root,'planning/Q4/model_spec.md')),'Use canonical Q4 output and specification');
  await fs.mkdir(temp,{recursive:true});
  if(args.previewTemplate){
    const {FileBlob,SpreadsheetFile}=await loadTool(temp);
    const original=await SpreadsheetFile.importXlsx(await FileBlob.load(template));
    const preview=await render(original,'A1:F5',path.join(temp,'template_native.png'));
    const receipt={template,template_sha256:TEMPLATE_SHA,preview,preview_sha256:await hashFile(preview),scope:'Native read-only original Q4 template preview; no workbook edits or authoring marker.'};
    insist(await hashFile(template)===TEMPLATE_SHA,'Read-only template changed');
    await fs.writeFile(path.join(temp,'template_preview.json'),JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));return;
  }
  insist(args.input && args.metadata && args.verification.length>0,'Actual accepted NPZ, metadata and verification paths must be supplied after the run exists');
  const input=path.resolve(root,args.input),metadata=path.resolve(root,args.metadata);
  insist(path.relative(path.join(root,'output/Q4'),input) && !path.relative(path.join(root,'output/Q4'),input).startsWith('..') && input.endsWith('.npz'),'Choose the actual Q4 main NPZ in output/Q4');
  insist(samePath(metadata,input.replace(/\.npz$/,'.json')),'Choose matching original Q4 metadata');
  insist(args['template-reviewed-sha']===TEMPLATE_SHA,'Pass the actually visually reviewed template identity');
  const previewReceipt=JSON.parse(await fs.readFile(path.join(temp,'template_preview.json'),'utf8'));
  insist(previewReceipt.template_sha256===TEMPLATE_SHA && await hashFile(previewReceipt.preview)===previewReceipt.preview_sha256,'Reviewed original template preview changed');
  for(const p of [output,auditOutput,summaryOutput])insist(await absent(p),`Do not overwrite an existing Q4 identity: ${p}`);
  const started=performance.now(),reportPath=path.join(temp,'q4_export_report.json');
  const report={status:'started',question:'Q4',operation_id:OPERATION_ID,input,metadata,output,template,template_sha256:TEMPLATE_SHA,
    exporter_sha256:await hashFile(fileURLToPath(import.meta.url)),memory_samples:[],native_previews:[],native_inspections:[],
    units:{time:'s',fixed_radius:'cm',surface_radius:'m in machine summary; moving surface column in workbook',moisture:'kg water/kg dry solid'},
    rounding:'Numeric binary64 values rounded to four decimal places, ties away from zero; independently checked with Decimal.from_float. Outside-domain cells stay genuinely empty.'};
  const memory=label=>{const sample={label,...process.memoryUsage()};report.memory_samples.push(sample);insist(sample.rss<=args.rssLimit*1048576,`RSS limit exceeded at ${label}`);};
  try{
    const state=JSON.parse(await fs.readFile(path.join(root,'.modeling/state.json'),'utf8'));
    const bindings={};
    // The model spec and shared inputs are frozen prerequisites. New result,
    // metadata, solver and reports may be verified S5 artifacts awaiting their
    // normal batch acceptance; no extra freeze/phase transition is introduced.
    for(const [role,p] of Object.entries({specification,input_npz:input,metadata,radius:geometry,boundary,solver:path.join(root,'src/Q4/solve.py')}))bindings[role]=await readBinding(state,root,p,{requireFrozen:['specification','radius','boundary'].includes(role),checkRegistered:['input_npz','metadata'].includes(role)});
    const meta=JSON.parse(await fs.readFile(metadata,'utf8'));
    insist(Number.isInteger(meta.grid_n) && meta.grid_n>=20 && meta.grid_n%20===0 && meta.tight===false && meta.method==='material_coordinate_nodal_finite_volume_segmented_BDF','Official ordinary main grid/tight/method contract mismatch');
    insist(meta.spec_sha256===bindings.specification.sha256 && meta.result_sha256===bindings.input_npz.sha256 && meta.radius_json_sha256===bindings.radius.sha256 && meta.boundary_sha256===bindings.boundary.sha256 && meta.solver_sha256===bindings.solver.sha256,'Actual main-run provenance bindings disagree');
    insist(samePath(meta.spec_path,specification) && samePath(meta.radius_path,geometry) && samePath(meta.boundary_path,boundary) && samePath(meta.output_path,input),'Main-run original paths disagree');
    const evidence=[],axes=new Set(),comparisonChecks=new Set();let boundInE2=false,boundInE3=false;
    for(const supplied of args.verification){
      const p=path.resolve(root,supplied),binding=await readBinding(state,root,p),v=JSON.parse(await fs.readFile(p,'utf8'));
      insist(v.passed===true && Array.isArray(v.checks) && v.checks.length>0 && v.checks.every(c=>c.passed===true) && Array.isArray(v.axes) && v.identities && typeof v.identities==='object',`Actual passing verifier report required: ${p}`);
      const identities=Object.entries(v.identities);
      const hasInput=identities.some(([p,h])=>samePath(p,input)&&h===bindings.input_npz.sha256);
      const hasMeta=identities.some(([p,h])=>samePath(p,metadata)&&h===bindings.metadata.sha256);
      for(const role of ['specification','radius','boundary','solver'])insist(identities.some(([p,h])=>samePath(p,bindings[role].path)&&h===bindings[role].sha256),`Verification ${p} must bind the actual ${role}`);
      if(v.mode==='compare'){
        insist(hasInput && hasMeta,`Process-comparison report must bind the selected main NPZ and metadata: ${p}`);
        const selected=v.details?.selected_main;
        insist(selected && samePath(selected.result,input) && selected.result_sha256===bindings.input_npz.sha256 && samePath(selected.metadata,metadata) && selected.metadata_sha256===bindings.metadata.sha256,`Target merely appears among compared runs; exact selected_main binding is required: ${p}`);
        insist(selected.grid_n===meta.grid_n && selected.tight===false && selected.method===meta.method && selected.scenario===meta.scenario && selected.properties===meta.properties && selected.radius_method===meta.radius.method,`Selected main grid/scenario/method identity mismatch: ${p}`);
        if(v.axes.includes('E2'))boundInE2=true;
        if(v.axes.includes('E3'))boundInE3=true;
        for(const check of v.checks)comparisonChecks.add(check.id);
      }
      for(const axis of v.axes)axes.add(axis);
      evidence.push({...binding,axes:v.axes,mode:v.mode,passed_checks:v.checks.length,binds_main_npz:hasInput,binds_main_metadata:hasMeta,
        selected_main:v.details?.selected_main??null,optional_run_identities:v.details?.run_identities??null,reuse:'Read existing evidence; this exporter does not rerun the verifier or solver.'});
    }
    insist(['E1','E2','E3'].every(axis=>axes.has(axis)) && boundInE2 && boundInE3,'Actual passing E1/E2/E3 coverage and main-run E2/E3 comparisons are required');
    insist(['selected_spatial_temperature','selected_spatial_moisture','selected_spatial_crossing','independent_time_temperature','independent_time_moisture','independent_time_crossing','both_prespecified_input_sensitivities_present'].every(id=>comparisonChecks.has(id)),'Actual process space/time and both input-sensitivity checks must be present; standalone axes alone are insufficient');
    report.bindings=bindings;report.prior_verification=evidence;
    const manifest=JSON.parse(await run(PYTHON,['-B','-c',PREPARE,input,metadata,geometry,temp]));report.input_manifest=manifest;
    insist(manifest.input_npz_sha256===bindings.input_npz.sha256 && manifest.metadata_sha256===bindings.metadata.sha256 && manifest.radius_json_sha256===bindings.radius.sha256,'Interchange source identity mismatch');
    const summary=path.join(temp,'summary_values.json'),summaryObject=JSON.parse(await fs.readFile(summary,'utf8'));
    Object.assign(summaryObject,{specification:bindings.specification,source_bindings:bindings,prior_verification:evidence,generator_sha256:report.exporter_sha256});
    await fs.writeFile(summary,JSON.stringify(summaryObject,null,2));
    const {FileBlob,SpreadsheetFile}=await loadTool(temp);
    const workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(template));
    const sheet=workbook.worksheets.getItem('Sheet1');
    // First and only actual workbook mutation is marked immediately here.
    report.operation_marker=await markerOnce(temp,output);
    sheet.getRange('W1').copyFrom(sheet.getRange('F1'),'all');
    sheet.getRange('B1:V1').copyFrom(sheet.getRange('B1'),'all');
    sheet.getRange('B1:V1').values=[manifest.radius_m.map(v=>Number((v*100).toFixed(1)))];
    sheet.getRange('B1:V1').setNumberFormat('0.0');sheet.getRange('W1').values=[['药材表面']];
    sheet.getRange('A1').format.columnWidth=29;sheet.getRange('B1:V1').format.columnWidth=11;sheet.getRange('W1').format.columnWidth=13;
    sheet.getRange('A1:W1').format.rowHeight=17;
    // Remove the original illustrative ellipsis; no observed/model value is edited.
    sheet.getRange('A2:F5').clear({applyTo:'contents'});
    if(manifest.data_rows<4)sheet.getRange(`A${manifest.data_rows+2}:F5`).clear({applyTo:'all'});
    const bytes=await fs.readFile(manifest.field.path);
    insist(await hashFile(manifest.field.path)===manifest.field.sha256 && bytes.length===manifest.data_rows*22*8,'Exact interchange size/hash');
    for(let first=0;first<manifest.data_rows;first+=512){
      const rows=Math.min(512,manifest.data_rows-first),start=first+2,stop=first+rows+1;
      const times=sheet.getRange(`A${start}:A${stop}`),body=sheet.getRange(`B${start}:W${stop}`);
      times.copyFrom(sheet.getRange('A2'),'all');body.copyFrom(sheet.getRange('B2'),'all');
      times.values=manifest.time_s.slice(first,first+rows).map(v=>[v]);
      body.values=Array.from({length:rows},(_,i)=>Array.from({length:22},(_,j)=>{
        const value=bytes.readDoubleLE(((first+i)*22+j)*8);
        insist(!Number.isNaN(value)||j<21,'Moving surface must always be a number');
        return Number.isNaN(value)?null:Number(value.toFixed(4));
      }));
      times.setNumberFormat('0');body.setNumberFormat('0.0000');sheet.getRange(`A${start}:W${stop}`).format.rowHeight=17;
      memory(`rows:${first+rows}/${manifest.data_rows}`);
    }
    sheet.freezePanes.freezeRows(1);sheet.freezePanes.freezeColumns(1);workbook.recalculate();
    const last=manifest.data_rows+1;
    const ranges=[['first',`A1:W${Math.min(last,9)}`],['middle',`A${Math.max(2,Math.floor(last/2)-3)}:W${Math.min(last,Math.max(2,Math.floor(last/2)-3)+7)}`],['last',`A${Math.max(1,last-7)}:W${last}`]];
    for(const [label,range] of ranges){
      report.native_inspections.push({label,range,ndjson:(await workbook.inspect({kind:'table',sheetId:'Sheet1',range,include:'values,formulas',tableMaxRows:9,tableMaxCols:23,maxChars:7000})).ndjson});
      report.native_previews.push(await render(workbook,range,path.join(temp,`moisture_${label}.png`)));memory(`native_render:${label}`);
    }
    report.formula_error_scan=(await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:25},maxChars:2500})).ndjson;
    memory('before_export');const exported=await SpreadsheetFile.exportXlsx(workbook);memory('after_export_before_save');
    const staged=path.join(temp,'result4.xlsx');insist(await absent(staged),'A prior staged Q4 workbook must be reviewed before reuse');await exported.save(staged);
    report.independent_verification=JSON.parse(await run(PYTHON,['-B','-c',AUDIT,staged,input,metadata,geometry,summary]));
    const checked=report.independent_verification;
    insist(checked.status==='pass',JSON.stringify(checked.errors));
    insist(checked.result_values_checked===manifest.total_numeric_field_values && checked.outside_blank_cells_checked===manifest.outside_blank_cells && checked.surface_values_checked===manifest.data_rows && checked.table6.cells_checked===manifest.table6_rows*6,'Complete dynamic output coverage required');
    for(const binding of [...Object.values(bindings),...evidence])insist(await hashFile(binding.path)===binding.sha256,`Verified evidence changed during export: ${binding.path}`);
    insist(await hashFile(template)===TEMPLATE_SHA && await hashFile(fileURLToPath(import.meta.url))===report.exporter_sha256,'Template/exporter changed');
    await fs.mkdir(path.dirname(output),{recursive:true});
    await place(staged,output,checked.xlsx_sha256);await place(summary,summaryOutput,checked.summary_sha256);
    report.elapsed_s=(performance.now()-started)/1000;
    const audit={schema:'q4_workbook_audit_v1',status:'awaiting_visual_review',data_status:'pass',output,
      input_npz:input,input_npz_sha256:bindings.input_npz.sha256,metadata,metadata_sha256:bindings.metadata.sha256,
      template,template_sha256:TEMPLATE_SHA,specification:bindings.specification,source_bindings:bindings,
      exporter_sha256:report.exporter_sha256,prior_verification:evidence,operation_id:OPERATION_ID,
      n_end_s:manifest.terminal_time_s,data_rows:manifest.data_rows,columns:23,units:report.units,rounding:report.rounding,
      independent_verification:checked,native_previews:report.native_previews,
      native_render_scope:'First, middle and last ranges of the complete artifact-tool authoring workbook; final saved XLSX independently audited against raw NPZ in full.',
      visual_review:{status:'pending',note:'Actually inspect all three PNGs. Outside-domain cells must remain empty; W is the actual moving surface. Displayed 0.1500 at an endpoint can be rounding of a strictly smaller raw value.'},
      memory_samples:report.memory_samples,elapsed_s:report.elapsed_s,detailed_report:reportPath};
    await fs.writeFile(auditOutput,JSON.stringify(audit,null,2),{flag:'wx'});report.status='data_pass_visual_pending';
    await fs.writeFile(reportPath,JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,output,audit:auditOutput,summary:summaryOutput,sha256:checked.xlsx_sha256,n_end_s:manifest.terminal_time_s,values_checked:checked.result_values_checked,outside_blank_cells_checked:checked.outside_blank_cells_checked}));
  }catch(e){report.status='fail';report.error=e.stack||String(e);report.elapsed_s=(performance.now()-started)/1000;await fs.writeFile(reportPath,JSON.stringify(report,null,2));throw e;}
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
