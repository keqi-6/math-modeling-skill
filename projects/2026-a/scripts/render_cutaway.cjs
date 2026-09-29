/* Render the exact cutaway geometry using a pinned Three.js module and Edge. */
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'..');
const OUT=path.join(ROOT,'output/paper_figures/redesign_v3');
const RUNTIME='C:/Users/35190/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const {chromium}=require(path.join(RUNTIME,'playwright'));
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const MIME={'.html':'text/html','.js':'text/javascript','.json':'application/json'};
const server=http.createServer((req,res)=>{
 const rel=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname).replace(/^\/+/, '');
 const file=path.resolve(ROOT,rel);
 if(!file.startsWith(ROOT+path.sep)){res.writeHead(403).end();return;}
 fs.readFile(file,(err,b)=>{if(err){res.writeHead(404).end();return;}
  res.writeHead(200,{'Content-Type':MIME[path.extname(file)]||'application/octet-stream'});res.end(b);});
});
function colorsSvg(){
 const colors=['#eaf3f7','#d6eff5','#99d3e1','#469dbf','#155c88'];
 return colors.map((c,i)=>`<stop offset="${i*25}%" stop-color="${c}"/>`).join('');
}
function svgLayer(png,text=true){
 const o=text?1:0;
 return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1400" height="820" viewBox="0 0 1400 820">
 <defs><linearGradient id="moist" x1="0" y1="1" x2="0" y2="0">${colorsSvg()}</linearGradient></defs>
 <rect width="1400" height="820" fill="white"/>
 <image x="10" y="-30" width="1280" height="940" xlink:href="${png}"/>
 <path d="M160 56H260" stroke="#db705e" stroke-width="7"/><path d="M260 56L237 44V68Z" fill="#db705e"/>
 <path d="M725 56H825" stroke="#2386ad" stroke-width="7"/><path d="M825 56L802 44V68Z" fill="#2386ad"/>
 <rect x="1220" y="225" width="35" height="490" fill="url(#moist)" stroke="#516674" stroke-width="1.5"/>
 ${[0,.5,1,1.5,2,2.55].map(c=>{const y=715-c/2.55*490;return `<path d="M1255 ${y}h10" stroke="#516674" stroke-width="2"/><text x="1276" y="${y+9}" font-size="29" opacity="${o}">${c}</text>`}).join('')}
 <g font-family="Microsoft YaHei, sans-serif" font-size="33" fill="#354650" opacity="${o}">
 <text x="287" y="67">热量传入</text><text x="852" y="67">水分迁出</text>
 <text x="1235" y="140" text-anchor="middle">干基</text><text x="1235" y="183" text-anchor="middle">含水率</text>
 <text x="1235" y="772" text-anchor="middle" font-size="29">kg/kg</text>
 </g></svg>`;
}
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try{
  browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,
   args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:2});
  page.on('pageerror',e=>console.error(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/output/paper_figures/redesign_v3/cutaway_scene.html`);
  await page.waitForFunction(()=>window.__READY__===true,{timeout:60000});
  const image=await page.evaluate(()=>document.querySelector('canvas').toDataURL('image/png'));
  const svg=svgLayer(image,true);
  fs.writeFileSync(path.join(OUT,'fig_mechanism_cutaway.svg'),svg);
  await page.setViewportSize({width:1400,height:820});
  const wrap=s=>`<!doctype html><meta charset="utf-8"><style>html,body{margin:0;width:1400px;height:820px}svg{display:block;width:100%;height:100%}@page{size:158mm 92.542857mm;margin:0}@media print{html,body{width:158mm;height:92.542857mm}}</style>${s}`;
  await page.setContent(wrap(svg));await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:path.join(OUT,'fig_mechanism_cutaway.png')});
  await page.pdf({path:path.join(OUT,'fig_mechanism_cutaway.pdf'),printBackground:true,preferCSSPageSize:true});
  await page.setContent(wrap(svgLayer(image,false)));
  await page.screenshot({path:path.join(OUT,'cutaway_textfree.png')});
  const input=JSON.parse(fs.readFileSync(path.join(OUT,'cutaway_data.json'),'utf8'));
  const files=['fig_mechanism_cutaway.svg','fig_mechanism_cutaway.png','fig_mechanism_cutaway.pdf','cutaway_textfree.png'];
  const manifest={status:'working_candidate',renderer:'Three.js 0.180.0; headless Edge/SwiftShader; orthographic camera',
   source:{path:input.source_path,sha256:input.source_sha256},time_s:1800,
   representation:input.geometry,encoding:input.encoding,palette:input.colors,C_range:input.C_range,
   mesh:{radial_subdivisions:128,angular_subdivisions:180,interpolation:'linear sampling of the stored 10241-node radial field for display only'},
   export:'Hybrid scientific image: high-resolution 3D raster inside SVG/PDF, with vector text and colorbar. Editable geometry in cutaway_scene.html.',
   three_source:'https://registry.npmjs.org/three/-/three-0.180.0.tgz',
   files:Object.fromEntries(files.map(f=>[f,{sha256:sha(path.join(OUT,f)),bytes:fs.statSync(path.join(OUT,f)).size}]))};
  fs.writeFileSync(path.join(OUT,'cutaway_sources.json'),JSON.stringify(manifest,null,2));
  console.log('Rendered cutaway SVG/PDF/PNG and text-free review image.');
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
