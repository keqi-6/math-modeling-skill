/** Conditional Q2 streaming fallback. TEMP preparation; never run implicitly.
 * Requires an actual artifact failure record, explicit --author, and the existing
 * successful operation marker for the same output. It never marks a second time.
 * Authoring is independent OOXML assembly; only PREPARE/AUDIT helpers are reused.
 */
import fs from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const RUNTIME = 'C:/Users/35190/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const PYTHON = `${RUNTIME}/python/python.exe`;
const MODULES = `${RUNTIME}/node/node_modules`;
const TEMPLATE_SHA = '23b261b295c1b787d000eebbca6521c37075107b6fcf78724f8d395ce1798ff4';
const SHEETS = [['温度', 'temperature'], ['水分浓度', 'moisture']];
const insist = (ok, message) => { if (!ok) throw new Error(message); };
const samePath = (a, b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

async function digest(p) {
  const h = crypto.createHash('sha256');
  for await (const b of createReadStream(p)) h.update(b);
  return h.digest('hex');
}

function run(executable, argv, progress = false) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, argv, { windowsHide: true });
    let stdout = '', stderr = '';
    child.stdout.on('data', data => { stdout += data; });
    child.stderr.on('data', data => {
      stderr = (stderr + data).slice(-20000);
      if (progress) process.stderr.write(data);
    });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve(stdout) : reject(new Error(`Child exit ${code}: ${stderr || stdout}`)));
  });
}

function argsFrom(argv) {
  if (argv.includes('--help')) return null;
  insist(argv.includes('--author'), 'Design-only by default. Explicit --author is required after actual failure and runtime admission.');
  const tokens = argv.filter(a => a !== '--author');
  const allowed = new Set(['project-root', 'input', 'metadata', 'template', 'output', 'failure-evidence', 'marker-receipt', 'preview-dir', 'chunk-rows']);
  const a = {};
  for (let i = 0; i < tokens.length; i += 2) {
    const key = tokens[i]?.replace(/^--/, '');
    insist(tokens[i]?.startsWith('--') && allowed.has(key) && !(key in a), `Invalid option: ${tokens[i]}`);
    insist(tokens[i + 1] && !tokens[i + 1].startsWith('--'), `Missing --${key}`);
    a[key] = tokens[i + 1];
  }
  for (const key of ['project-root', 'input', 'metadata', 'template', 'output', 'failure-evidence']) insist(a[key], `Required --${key}`);
  a.chunkRows = Number(a['chunk-rows'] ?? 1024);
  insist(Number.isInteger(a.chunkRows) && a.chunkRows >= 32 && a.chunkRows <= 8192, 'chunk-rows must be 32..8192.');
  return a;
}

const AUTHOR = String.raw`
import sys, json, zipfile, hashlib, copy, struct, math, time, shutil
from pathlib import Path
import xml.etree.ElementTree as ET
manifest_path, template, output = map(Path,sys.argv[1:4]);chunk=int(sys.argv[4])
manifest=json.loads(manifest_path.read_text(encoding='utf-8'));end=manifest['n_end']
assert type(end) is int and 1<=end<=1048575
M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RID='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
ET.register_namespace('',M[1:-1]);ET.register_namespace('r',RID[1:-3])
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def encode(element):return ET.tostring(element,encoding='utf-8',xml_declaration=True)
def rounded_literal(value):
    assert math.isfinite(value) and abs(value)<1e12
    numerator,denominator=value.as_integer_ratio()
    q,remainder=divmod(abs(numerator)*10000,denominator)
    if 2*remainder>=denominator:q+=1
    sign='-' if numerator<0 and q else ''
    return sign+str(q//10000)+'.'+str(q%10000).zfill(4)
assert digest(template)=='23b261b295c1b787d000eebbca6521c37075107b6fcf78724f8d395ce1798ff4'
assert digest(manifest['input_npz'])==manifest['input_npz_sha256']
assert digest(manifest['metadata'])==manifest['metadata_sha256']
for field in ('temperature_C','moisture_kg_kg'):
    info=manifest['fields'][field]
    assert info['shape']==[end,21] and info['dtype']=='<f8'
    assert Path(info['path']).stat().st_size==end*21*8 and digest(info['path'])==info['sha256']
changed={'xl/styles.xml','xl/sharedStrings.xml','xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml'}
started=time.perf_counter();counts=[];unchanged={};template_structures=[]
with zipfile.ZipFile(template) as original:
    names=original.namelist();assert len(names)==len(set(names))==12
    workbook=ET.fromstring(original.read('xl/workbook.xml'))
    sheets=workbook.findall(M+'sheets/'+M+'sheet')
    assert [s.get('name') for s in sheets]==['温度','水分浓度']
    relationships={r.get('Id'):r.get('Target') for r in ET.fromstring(original.read('xl/_rels/workbook.xml.rels'))}
    assert [relationships[s.get(RID)] for s in sheets]==['worksheets/sheet1.xml','worksheets/sheet2.xml']
    for sheetfile in ('xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml'):
        root=ET.fromstring(original.read(sheetfile));template_structures.append(root)
        assert not list(root.iter(M+'f')) and not list(root.iter(M+'mergeCell'))
    original_xfs=ET.fromstring(original.read('xl/styles.xml')).find(M+'cellXfs')
    original_data_style=int(template_structures[0].find(M+'sheetData/'+M+'row[@r="2"]/'+M+'c[@r="B2"]').get('s','0'))
    original_time_style=int(template_structures[0].find(M+'sheetData/'+M+'row[@r="2"]/'+M+'c[@r="A2"]').get('s','0'))
    original_header_style=int(template_structures[0].find(M+'sheetData/'+M+'row[@r="1"]/'+M+'c[@r="B1"]').get('s','0'))
    styles=ET.fromstring(original.read('xl/styles.xml'));xfs=styles.find(M+'cellXfs')
    formats=styles.find(M+'numFmts')
    if formats is None:formats=ET.Element(M+'numFmts');styles.insert(0,formats)
    fmtid=max([163]+[int(f.get('numFmtId')) for f in formats])+1
    newstyles=[]
    for original_style,code in ((original_data_style,'0.0000'),(original_header_style,'0.0')):
        ET.SubElement(formats,M+'numFmt',numFmtId=str(fmtid),formatCode=code)
        xf=copy.deepcopy(xfs[original_style]);xf.set('numFmtId',str(fmtid));xf.set('applyNumberFormat','1')
        newstyles.append(len(xfs));xfs.append(xf);fmtid+=1
    formats.set('count',str(len(formats)));xfs.set('count',str(len(xfs)))
    body_style,header_style=newstyles
    shared=ET.fromstring(original.read('xl/sharedStrings.xml'));shared.set('count','2')
    replacement={'xl/styles.xml':encode(styles),'xl/sharedStrings.xml':encode(shared)}
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as final:
        for member in original.infolist():
            if member.filename in changed:continue
            h=hashlib.sha256()
            with original.open(member) as source,final.open(copy.copy(member),'w') as target:
                for block in iter(lambda:source.read(1024*1024),b''):h.update(block);target.write(block)
            unchanged[member.filename]=h.hexdigest()
        for name,content in replacement.items():final.writestr(name,content)
        for index,(sheetfile,field) in enumerate(zip(('xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml'),('temperature_C','moisture_kg_kg'))):
            root=copy.deepcopy(template_structures[index]);root.find(M+'dimension').set('ref','A1:V'+str(end+1))
            sheetdata=root.find(M+'sheetData')
            a1=copy.deepcopy(sheetdata.find(M+'row[@r="1"]/'+M+'c[@r="A1"]'))
            assert a1 is not None and a1.get('t')=='s'
            sheetdata.clear()
            view=root.find(M+'sheetViews/'+M+'sheetView')
            for existing in list(view):
                if existing.tag in (M+'pane',M+'selection'):view.remove(existing)
            view.insert(0,ET.Element(M+'pane',xSplit='1',ySplit='1',topLeftCell='B2',activePane='bottomRight',state='frozen'))
            view.append(ET.Element(M+'selection',pane='bottomRight',activeCell='B2',sqref='B2'))
            cols=root.find(M+'cols');priorcols=list(cols);cols.clear()
            col_a=copy.deepcopy(priorcols[0]);col_a.attrib.update(min='1',max='1',width='29',customWidth='1');cols.append(col_a)
            col_b=copy.deepcopy(priorcols[1]);col_b.attrib.update(min='2',max='22',width='11',customWidth='1');cols.append(col_b)
            # Original remainder begins at G; only the unused W:XFD part remains.
            remainder=copy.deepcopy(priorcols[-1]);remainder.set('min','23');cols.append(remainder)
            serialized=encode(root);sentinel=b'<sheetData />';assert serialized.count(sentinel)==1
            prefix,suffix=serialized.split(sentinel)
            header=ET.Element(M+'row',r='1',spans='1:22',ht='17',customHeight='1');header.append(a1)
            for j in range(21):
                cell=ET.SubElement(header,M+'c',r=chr(66+j)+'1',s=str(header_style))
                ET.SubElement(cell,M+'v').text=str(j//10) if j%10==0 else str(j//10)+'.'+str(j%10)
            written=0
            with final.open(sheetfile,'w',force_zip64=True) as target,open(manifest['fields'][field]['path'],'rb') as source:
                target.write(prefix+b'<sheetData>');target.write(ET.tostring(header,encoding='utf-8'))
                for first in range(0,end,chunk):
                    rows=min(chunk,end-first);data=source.read(rows*21*8);assert len(data)==rows*21*8
                    values=iter(struct.iter_unpack('<d',data));text=[]
                    for i in range(rows):
                        second=first+i+1;row=second+1
                        cells=[f'<row r="{row}" spans="1:22" ht="17" customHeight="1"><c r="A{row}" s="{original_time_style}"><v>{second}</v></c>']
                        for j in range(21):
                            lexical=rounded_literal(next(values)[0]);cells.append(f'<c r="{chr(66+j)}{row}" s="{body_style}"><v>{lexical}</v></c>')
                        cells.append('</row>');text.append(''.join(cells));written+=21
                    target.write(''.join(text).encode('utf-8'))
                    if first==0 or first+rows==end or (first//chunk)%4==0:
                        elapsed=time.perf_counter()-started
                        print(json.dumps({'phase':'stream_write','field':field,'rows_written':first+rows,'field_rows':end,'elapsed_s':elapsed}),file=sys.stderr,flush=True)
                assert not source.read(1)
                target.write(b'</sheetData>'+suffix)
            assert written==end*21;counts.append({'field':field,'values':written})
with zipfile.ZipFile(output) as final,zipfile.ZipFile(template) as original:
    assert len(final.namelist())==12 and set(final.namelist())==set(original.namelist())
    for name,expected in unchanged.items():assert hashlib.sha256(final.read(name)).hexdigest()==expected
    # Existing styles must be unchanged semantically; only two XFs and formats append.
    actual=ET.fromstring(final.read('xl/styles.xml'));before=ET.fromstring(original.read('xl/styles.xml'))
    actual_xfs=actual.find(M+'cellXfs')
    for i,xf in enumerate(before.find(M+'cellXfs')):assert ET.tostring(xf)==ET.tostring(actual_xfs[i])
    for element in before:
        if element.tag not in (M+'cellXfs',M+'numFmts'):
            assert ET.tostring(element)==ET.tostring(actual.find(element.tag))
    # The independent auditor consumes both large sheet members fully, checking
    # their ZIP CRC as it reads. Avoid a redundant full-file testzip pass here.
assert digest(manifest['input_npz'])==manifest['input_npz_sha256'] and digest(manifest['metadata'])==manifest['metadata_sha256']
print(json.dumps({'status':'pass','output':str(output),'n_end':end,'sheets':counts,'unchanged_members':unchanged,
 'changed_members':sorted(changed),'appended_style_ids':newstyles,'rounding_implementation':'exact binary64 integer ratio, nearest 1e-4, ties away from zero',
 'elapsed_s':time.perf_counter()-started,'sha256':digest(output),'bytes':output.stat().st_size},ensure_ascii=False))
`;

const PROJECTIONS = String.raw`
import sys,json,zipfile,io,base64,copy
from pathlib import Path
import xml.etree.ElementTree as ET
book=Path(sys.argv[1]);end=int(sys.argv[2]);last=end+1
M='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
ET.register_namespace('',M[1:-1]);ET.register_namespace('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships')
starts={'first':2,'middle':max(2,last//2-3),'last':max(2,last-7)}
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
                    # Rebased coordinates are the only cell/row changes in this projection.
                    restored=copy.deepcopy(row);restored.set('r',str(old_row))
                    for cell in restored:
                        letters=''.join(c for c in cell.get('r') if c.isalpha());cell.set('r',letters+str(old_row))
                    assert ET.tostring(restored)==ET.tostring(selected[name][old_row])
                crop.writestr(name,ET.tostring(root,encoding='utf-8',xml_declaration=True))
        packages.append({'label':label,'source_rows':[1]+rows,'render_range':'A1:V'+str(len(rows)+1),
            'projection_rows':list(range(1,len(rows)+2)),'base64':base64.b64encode(buffer.getvalue()).decode('ascii')})
print(json.dumps({'scope':'Read-only range projections extracted from final XLSX XML; not a full-workbook engine import','packages':packages}))
`;

async function loadTool(temp) {
  const link = path.join(temp, 'node_modules');
  try { await fs.symlink(MODULES, link, 'junction'); }
  catch (e) { if (e.code !== 'EEXIST') throw e; insist(samePath(await fs.realpath(link), await fs.realpath(MODULES)), 'Wrong dependency junction.'); }
  const resolve = createRequire(path.join(temp, 'resolve.cjs'));
  return import(pathToFileURL(resolve.resolve('@oai/artifact-tool')).href);
}

async function main() {
  const args = argsFrom(process.argv.slice(2));
  if (!args) { console.log('Design-only unless --author. Required: --project-root --input --metadata --template --output --failure-evidence. Optional: --marker-receipt --preview-dir --chunk-rows.'); return; }
  const root = path.resolve(args['project-root']);
  const input = path.resolve(root,args.input), metadata = path.resolve(root,args.metadata);
  const template = path.resolve(root,args.template), output = path.resolve(root,args.output);
  const failure = path.resolve(root,args['failure-evidence']);
  insist(samePath(output,path.join(root,'output/Q2/result2.xlsx')), 'Only the admitted final result2.xlsx is allowed.');
  insist(samePath(template,path.join(root,'附件/附件3/result2.xlsx')) && await digest(template) === TEMPLATE_SHA, 'Template identity mismatch.');
  const failureRecord = JSON.parse(await fs.readFile(failure,'utf8'));
  insist(failureRecord.status === 'fail' && failureRecord.tool === '@oai/artifact-tool' &&
    failureRecord.failure_kind === 'configured_RSS_limit_exceeded' && failureRecord.process_exit_observed === true,
    'A completed, controlled artifact-tool memory failure is required for this fallback.');
  const priorReportPath = path.resolve(failureRecord.failure_report);
  insist(await digest(priorReportPath) === failureRecord.failure_report_sha256,'Prior failure report identity changed.');
  const priorReport = JSON.parse(await fs.readFile(priorReportPath,'utf8'));
  const lastMemory = priorReport.memory_samples?.at(-1);
  insist(priorReport.status === 'fail' && samePath(priorReport.input,input) && samePath(priorReport.metadata,metadata) &&
    samePath(priorReport.output,output) && lastMemory?.rss === failureRecord.last_rss_bytes &&
    lastMemory.rss > failureRecord.configured_rss_limit_mib * 1048576 &&
    priorReport.memory_samples.length === failureRecord.memory_sample_count,
    'Failure evidence does not describe the same completed full-table attempt.');
  const receiptPath = path.resolve(args['marker-receipt'] ?? path.join(os.tmpdir(),'cumcm-q2-workbook/artifact_operation_started.json'));
  const receipt = JSON.parse(await fs.readFile(receiptPath,'utf8'));
  insist(receipt.status === 'success' && samePath(receipt.output,output), 'Requires the existing successful marker for this exact output. No second marker is called.');
  insist(await digest(receiptPath) === failureRecord.marker_receipt_sha256,'The single prior marker receipt changed.');
  const temp = path.resolve(args['preview-dir'] ?? path.join(os.tmpdir(),'cumcm-q2-workbook-fallback'));
  const relative = path.relative(os.tmpdir(),temp);
  insist(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'All fallback intermediates must stay inside TEMP.');
  await fs.mkdir(temp,{recursive:true});
  const sourceExporter = path.join(root,'src/Q2/export_workbook.mjs');
  const sourceText = await fs.readFile(sourceExporter,'utf8');
  const helper = name => {
    const code = new RegExp('const '+name+' = String\\.raw`([\\s\\S]*?)`;').exec(sourceText)?.[1];
    insist(code,`Could not read explicitly reused ${name} helper.`); return code;
  };
  const reportPath = path.join(temp,'q2_stream_report.json');
  const failureSummary = {
    source_record:failure,source_record_sha256:await digest(failure),
    detailed_report:priorReportPath,detailed_report_sha256:failureRecord.failure_report_sha256,
    tool:failureRecord.tool,scope:'This complete two-sheet authoring task exceeded the configured memory budget on this host; small artifact-tool imports/renders remain available.',
    failure_kind:failureRecord.failure_kind,reason:failureRecord.error,
    runtime_action_id:failureRecord.runtime_action_id,grant_id:failureRecord.grant_id,command_hash:failureRecord.command_hash,
    exit_code:failureRecord.exit_code,elapsed_s:failureRecord.bounded_elapsed_s,
    last_field:failureRecord.last_completed_field,completed_field_rows:failureRecord.last_completed_field_rows,
    required_field_rows:failureRecord.required_rows_per_field,last_rss_bytes:lastMemory.rss,
    configured_rss_limit_mib:failureRecord.configured_rss_limit_mib,memory_sample_count:priorReport.memory_samples.length,
    memory_samples:priorReport.memory_samples.map(({label,rss,heapUsed})=>({label,rss,heap_used_bytes:heapUsed})),
    original_exporter_sha256:priorReport.exporter_sha256,marker_receipt_sha256:failureRecord.marker_receipt_sha256,
  };
  const report = { status:'started', authoring_route:'conditional_streaming_OOXML', output,
    fallback_builder_sha256:await digest(fileURLToPath(import.meta.url)), reused_helper_source:sourceExporter,
    reused_helper_source_sha256:await digest(sourceExporter),failure_evidence:failure,failure_evidence_sha256:await digest(failure),
    marker_receipt:receiptPath,marker_receipt_sha256:await digest(receiptPath),operation_marker:'reused_existing_success_no_second_marker',
    template_sha256:TEMPLATE_SHA,fallback_failure_evidence:failureSummary,previews:[],projection_mappings:[] };
  try {
    const manifest = JSON.parse(await run(PYTHON,['-B','-c',helper('PREPARE'),input,metadata,temp,String(args.chunkRows)]));
    report.input_manifest = manifest;
    const staged = path.join(temp,'result2.xlsx');
    // First and only full-workbook authoring path in this fallback.
    report.streaming_write = JSON.parse(await run(PYTHON,['-B','-c',AUTHOR,path.join(temp,'input_manifest.json'),template,staged,String(args.chunkRows)],true));
    report.independent_xml = JSON.parse(await run(PYTHON,['-B','-c',helper('AUDIT'),path.join(temp,'input_manifest.json'),staged]));
    insist(report.independent_xml.status === 'pass' && report.independent_xml.result_values_checked === manifest.n_end*42,'Full independent XML audit failed.');
    const projection = JSON.parse(await run(PYTHON,['-B','-c',PROJECTIONS,staged,String(manifest.n_end)]));
    report.preview_scope = projection.scope;
    const { FileBlob,SpreadsheetFile } = await loadTool(temp);
    const original = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
    for (const [name,slug] of SHEETS) {
      const png = await original.render({sheetName:name,range:'A1:F5',scale:1.5,format:'png'});
      const destination=path.join(temp,`template_${slug}.png`);await fs.writeFile(destination,new Uint8Array(await png.arrayBuffer()));report.previews.push(destination);
    }
    report.projection_checks = [];
    for (const part of projection.packages) {
      const bytes = Buffer.from(part.base64,'base64');
      const workbook = await SpreadsheetFile.importXlsx(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
      workbook.recalculate();
      report.projection_mappings.push({ label:part.label,source_rows:part.source_rows,projection_rows:part.projection_rows,range:part.render_range });
      for (const [name,slug] of SHEETS) {
        const inspected=await workbook.inspect({kind:'table',sheetId:name,range:part.render_range,include:'values,formulas',tableMaxRows:9,tableMaxCols:22,maxChars:6000});
        report.projection_checks.push({sheet:name,label:part.label,ndjson:inspected.ndjson});
        const png=await workbook.render({sheetName:name,range:part.render_range,scale:1.5,format:'png'});
        const destination=path.join(temp,`${slug}_${part.label}.png`);await fs.writeFile(destination,new Uint8Array(await png.arrayBuffer()));report.previews.push(destination);
      }
    }
    insist(await digest(template) === TEMPLATE_SHA,'Template changed during fallback.');
    insist(await digest(sourceExporter) === report.reused_helper_source_sha256,'Reused source helpers changed during fallback.');
    insist(await digest(staged) === report.independent_xml.xlsx_sha256,'Staged workbook changed after independent audit.');
    await fs.mkdir(path.dirname(output),{recursive:true});
    const destinationStage=path.join(path.dirname(output),'.result2.xlsx.staging');
    await fs.copyFile(staged,destinationStage);
    insist(await digest(destinationStage) === report.independent_xml.xlsx_sha256,'Cross-volume copy changed the verified workbook.');
    await fs.rename(destinationStage,output);
    insist(await digest(output) === report.independent_xml.xlsx_sha256,'Workbook changed during final placement.');
    report.status='data_pass_visual_pending';
    const audit={schema:'q2_workbook_audit_v1',status:'awaiting_visual_review',data_status:'pass',authoring_route:report.authoring_route,
      output,template,input_npz:input,metadata,input_npz_sha256:manifest.input_npz_sha256,metadata_sha256:manifest.metadata_sha256,
      template_sha256:TEMPLATE_SHA,exporter_sha256:report.fallback_builder_sha256,
      units:{time:'s',radius:'cm',temperature:'°C',moisture:'kg water/kg dry solid'},
      rounding:'Exact binary64 integer-ratio rounding to four decimal places, ties away from zero; numeric cells formatted 0.0000',
      fallback_failure_evidence:failureSummary,n_end:manifest.n_end,
      independent_xml:report.independent_xml,template_preservation:report.streaming_write,
      native_previews:report.previews,visual_review:{status:'pending',scope:report.preview_scope,mappings:report.projection_mappings},
      detailed_export_report:reportPath};
    await fs.writeFile(path.join(root,'output/Q2/workbook_audit.json'),JSON.stringify(audit,null,2));
    await fs.writeFile(reportPath,JSON.stringify(report,null,2));
    console.log(JSON.stringify({status:report.status,output,report:reportPath,values_checked:manifest.n_end*42,sha256:report.independent_xml.xlsx_sha256}));
  } catch (e) {
    report.status='fail';report.error=e.stack||String(e);await fs.writeFile(reportPath,JSON.stringify(report,null,2));throw e;
  }
}

main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
