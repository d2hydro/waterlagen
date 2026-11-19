const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const acorn=require('acorn');
const directory=path.resolve(__dirname,'../../tools/runscript_maken/web');
const script=fs.readFileSync(path.join(directory,'app.js'),'utf8');
acorn.parse(script,{ecmaVersion:'latest',sourceType:'module'});
const bootstrap=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const appearance=JSON.parse(fs.readFileSync(path.join(directory,'appearance.json'),'utf8'));
const dom=new JSDOM(fs.readFileSync(path.join(directory,'index.html'),'utf8'),{url:'http://127.0.0.1:12345/session/',runScripts:'outside-only',virtualConsole:new VirtualConsole()});
const window=dom.window;
const css=window.document.createElement('style');
css.textContent=fs.readFileSync(path.join(directory,'style.css'),'utf8');
window.document.head.append(css);
window.assert=assert;window.requests=[];
window.ResizeObserver=class{observe(){}};
if(!window.HTMLDialogElement.prototype.showModal){
 window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 window.HTMLDialogElement.prototype.close=function(){this.open=false;};
}
function matrix(a=1,d=1,e=0,f=0){return{a,b:0,c:0,d,e,f,inverse(){return matrix(1/a,1/d,-e/a,-f/d);}};}
window.SVGElement.prototype.getScreenCTM=function(){
 const match=(this.getAttribute('transform')||'').match(/translate\(([^ ]+) ([^)]+)\) scale\(([^)]+)\)/);
 return match?matrix(+match[3],+match[3],+match[1],+match[2]):matrix();
};
window.SVGElement.prototype.createSVGPoint=function(){return{x:0,y:0,matrixTransform(m){return{x:this.x*m.a+m.e,y:this.y*m.d+m.f};}};};
window.SVGElement.prototype.hasPointerCapture=()=>false;
window.SVGElement.prototype.setPointerCapture=()=>{};
const feature={type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[4.7,52.6],[4.7,52.61],[4.71,52.61],[4.71,52.6],[4.7,52.6]]]}};
window.fetch=async(url,init)=>{
 const action=String(url).replace('api/','');
 const values=init?JSON.parse(init.body):{};
 window.requests.push({action,values});
 let result={};
 if(action==='bootstrap'){result=bootstrap;}
 else if(action==='appearance.json'){result=appearance;}
 else if(action==='preview'){result={commands:['pixi run --locked dem --waterbeheercode 12']};}
 else if(action==='dem_landuse'){
  if(window.deferLanduse){
   window.deferLanduse=false;
   return new Promise(resolve=>window.finishLanduse=()=>resolve({ok:true,json:async()=>({state:'reuse',message:'Verouderde selectie',path:''})}));
  }
  result={state:'reuse',message:'Automatisch: landgebruikrun afgerond',path:'D:\\data\\afgerond'};
 }
 else if(action==='polygon_file'){result={path:window.pickPath||'D:\\gebieden.gpkg',layers:['west','oost']};}
 else if(action==='polygon_layer'){
  if(window.rejectLayer){
   window.rejectLayer=false;
   return {ok:false,json:async()=>({error:'De gebiedslaag moet uitsluitend geldige polygonen bevatten.'})};
  }
  if(window.deferLayer){
   window.deferLayer=false;
   return new Promise(resolve=>window.finishLayer=()=>resolve({ok:true,json:async()=>({feature,layers:['west','oost']})}));
  }
  result={feature,layers:['west','oost']};
 }
 else if(action==='draw_save'){result={path:'D:\\eigen-gebied.gpkg',layer:'gebied',feature};}
 else if(action==='bounds'){result={feature};}
 else if(action==='save'){result={path:'D:\\proef.bat',started:!!values.start};}
 else if(action==='run_load'){result=window.loadedRun||{mode:'authorities',authorities:['38'],layers:['inwoners'],run_id:'aa-en-maas',workers:16,run_mode:'overwrite',extra_options:[],debug:true,refresh_sources:false,path:'D:\\vorige.bat'};}
 else if(action==='browse' && window.deferBrowse){
  return new Promise(resolve=>window.cancelBrowse=()=>resolve({ok:true,json:async()=>({cancelled:true})}));
 }
 else if(action==='browse' && window.failBrowse){throw new TypeError('Failed to fetch');}
 else if(action==='browse' && window.invalidBrowse){result={path:'tekst.txt',error:'Kies een TOML-bestand.'};}
 else if(action==='validate_path' && values.path==='tekst.txt'){result={error:'Kies een TOML-bestand.'};}
 else if(action==='browse'){result={path:'D:\\brandlagen.toml'};}
 else if(action==='brand_edit'){result={path:window.cancelBrandEdit?'':'D:\\brandlagen-nieuw.toml'};}
 return {ok:true,json:async()=>result};
};
window.eval(fs.readFileSync(path.join(directory,'d3.min.js'),'utf8'));
const checks=`
 const assert=window.assert;
 const settle=()=>new Promise(resolve=>setTimeout(resolve,0));
 assert.equal(root.hidden,false);
 assert.equal(q('#rm-workers').value,'8');
 assert.equal(q('#rm-run-name').value,'kaartproef');
 assert.equal(root.querySelectorAll('[data-flag]').length,Object.values(data.options).flat().length);
 assert.equal(q('#rm-layers').children.length,5);
 assert.equal(q('#rm-background').getAttribute('aria-label'),'Luchtfoto tonen');
 assert(q('#rm-attribution a').href.includes('openstreetmap.org'));
 const originalZoom=zoom;
 setZoom(1);
 const overviewOpacity=Number(liveTiles.style.opacity);
 setZoom(8);
 const middleOpacity=Number(liveTiles.style.opacity);
 setZoom(128);
 assert(overviewOpacity < middleOpacity && middleOpacity < Number(liveTiles.style.opacity));
 assert.equal(Number(liveTiles.style.opacity),1);
 q('#rm-background').click();
 assert.equal(q('#rm-background').title,'Stratenkaart tonen');
 assert.equal(tileProvider,'satellite');setZoom(1);
 assert.equal(Number(liveTiles.style.opacity),overviewOpacity);
 assert.equal(q('.authority-casing').parentElement.getAttribute('pointer-events'),'none');
 q('#rm-background').click();assert.equal(tileProvider,'streets');setZoom(originalZoom);
 const landuseMode=q('#rm-dem-landuse-mode');
 const landuseField=q('[data-layer="dem"][data-flag="landuse-run"]');
 const landuseStatus=q('#rm-dem-landuse-status');
 assert.equal(landuseMode.value,'auto');
 assert(landuseField.disabled && landuseField.closest('label').hidden);
 assert(!collectValues().extra_options.some(o=>o.flag==='landuse-run'));
 await updateLandusePreview();
 assert.equal(landuseStatus.textContent,'Automatisch: landgebruikrun afgerond');
 landuseMode.value='manual';landuseMode.dispatchEvent(new Event('change',{bubbles:true}));
 assert(!landuseField.disabled && !landuseField.closest('label').hidden);
 assert(!landuseField.closest('label').querySelector('button').disabled);
 assert.equal(collectValues().dem_landuse_mode,'manual');
 landuseField.value='gekozen-run';
 assert(collectValues().extra_options.some(o=>o.flag==='landuse-run'&&o.value==='gekozen-run'));
 landuseMode.value='auto';landuseMode.dispatchEvent(new Event('change',{bubbles:true}));
 assert(!collectValues().extra_options.some(o=>o.flag==='landuse-run'));
 render();assert(landuseField.disabled,'Kaartbediening mag de verborgen map niet opnieuw activeren');
 window.deferLanduse=true;
 scheduleLandusePreview(true);const pendingPreview=updateLandusePreview();
 q('#rm-refresh').checked=true;q('#rm-refresh').dispatchEvent(new Event('change',{bubbles:true}));
 window.finishLanduse();await pendingPreview;await settle();
 assert(!landuseStatus.textContent.includes('Verouderde selectie'));
 q('#rm-refresh').checked=false;q('#rm-refresh').dispatchEvent(new Event('change',{bubbles:true}));
 landuseField.value='';
 for(const button of root.querySelectorAll('.option-actions button')){
  if(button.closest('.dem-landuse-group') && landuseMode.value==='auto'){
   assert(button.disabled && button.closest('label').hidden);
   continue;
  }
  assert(!button.disabled,'Bestanden kiezen moet ook voor niet-aangevinkte lagen werken');
 }
 for(const control of root.querySelectorAll('.file-control')){
  assert(control.querySelector('input[data-kind]'));
  assert(control.querySelector('button.file-browse svg'));
  assert(control.querySelector('button.file-browse').getAttribute('aria-label'));
 }
 // Klikken op de kaart en in de lijst geeft dezelfde selectie.
 q('[data-code="38"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));
 assert(selected.has('38'));assert(q('#rm-list input[value="38"]').checked);
 q('#rm-list input[value="38"]').click();assert(!selected.has('38'));
 const extra=optionButtons.get('dem');extra.click();
 assert.equal(optionPanels.get('dem').parentElement,root);
 assert(!optionPanels.get('dem').hidden);
 q('[data-layer="dem"][data-flag="building-workers"]').value='3';
 optionPanels.get('dem').querySelector('header button').click();extra.click();
 assert.equal(q('[data-layer="dem"][data-flag="building-workers"]').value,'3');
 root.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 assert(optionPanels.get('dem').hidden);
 q('#rm-preview').click();await settle();
 const scriptPreview=q('#rm-script-preview');
 assert(scriptPreview.open);assert(q('#rm-message').hidden);
 assert(scriptPreview.querySelector('pre').textContent.includes('pixi run --locked'));
 q('#rm-script-close').click();assert(!scriptPreview.open);
 q('#rm-preview').click();await settle();assert(scriptPreview.open);
 scriptPreview.click();assert(!scriptPreview.open);
 assert(window.requests.find(r=>r.action==='preview').values.extra_options.some(o=>o.flag==='building-workers'&&o.value==='3'));
 optionButtons.get('afwateringseenheden').click();
 const brandInput=q('[data-layer="afwateringseenheden"][data-kind="toml"]');
 const brandGroup=brandInput.closest('.brandlagen-group');
 const brandToggle=brandGroup.querySelector('.brandlagen-toggle');
 const brandContent=brandGroup.querySelector('.brandlagen-content');
 assert.equal(optionPanels.get('afwateringseenheden').querySelector('.extra-fields').firstElementChild,brandGroup);
 assert(brandContent.hidden);
 brandToggle.click();assert(!brandContent.hidden);
 brandToggle.click();assert(brandContent.hidden);
 brandToggle.click();
 const createBrand=brandContent.querySelector('button');
 const editBrand=brandContent.querySelector('.option-actions:last-child button');
 assert.equal(createBrand.textContent,'Nieuw maken');
 assert(brandContent.querySelector('.brandlagen-selected').hidden);
 assert(editBrand.hidden);
 const browseButton=brandContent.querySelector('.brandlagen-choices button:last-child');
 assert.equal(browseButton.textContent,'TOML kiezen');
 window.deferBrowse=true;browseButton.click();
 assert(browseButton.disabled);
 assert(q('#rm-message').hidden,'Het Windows-venster heeft geen extra wachtmelding nodig');
 window.cancelBrowse();window.deferBrowse=false;await settle();
 assert(q('#rm-message').hidden);assert(!browseButton.disabled);
 window.failBrowse=true;browseButton.click();await settle();
 assert(q('#rm-message').textContent.includes('run-maken.bat opnieuw'));
 assert(!browseButton.disabled);
 window.failBrowse=false;window.invalidBrowse=true;browseButton.click();await settle();
 const feedback=q('.file-error[id="rm-error-afwateringseenheden-brandlagen-config"]');
 assert.equal(brandInput.getAttribute('aria-invalid'),'true');
 assert.equal(feedback.textContent,'Kies een TOML-bestand.');
 assert(q('#rm-message').hidden,'Het bestandsveld toont de foutmelding');
 window.invalidBrowse=false;
 window.failBrowse=false;browseButton.click();await settle();
 assert(brandInput.value.endsWith('brandlagen.toml'));
 assert.equal(feedback.textContent,'');
 assert(!editBrand.hidden);
 assert(!brandContent.querySelector('.brandlagen-selected').hidden);
 editBrand.click();await settle();
 assert.equal(window.requests.filter(r=>r.action==='brand_edit').at(-1).values.path,'D:\\\\brandlagen.toml');
 assert(brandInput.value.endsWith('brandlagen-nieuw.toml'));
 window.cancelBrandEdit=true;createBrand.click();await settle();
 assert(brandInput.value.endsWith('brandlagen-nieuw.toml'),'Annuleren behoudt de gekozen TOML');
 window.cancelBrandEdit=false;createBrand.click();await settle();
 assert.equal(window.requests.filter(r=>r.action==='brand_edit').at(-1).values.path,'');
 assert(brandInput.value.endsWith('brandlagen-nieuw.toml'));
 assert(collectValues().extra_options.some(o=>o.flag==='brandlagen-config'&&o.value===brandInput.value));
 brandInput.value='tekst.txt';brandInput.dispatchEvent(new Event('change'));await settle();
 assert.equal(feedback.textContent,'Kies een TOML-bestand.');
 brandInput.value='';brandInput.dispatchEvent(new Event('input'));
 assert.equal(feedback.textContent,'');assert(editBrand.hidden);
 assert(brandContent.querySelector('.brandlagen-selected').hidden);
 closeOptions();
 // Het oude maximum van 32 is ruim gepasseerd.
 const overviewZoom=zoom;
 for(let i=0;i<20;i++){q('#rm-zoom-in').click();}
 assert(zoom>32);q('#rm-reset').click();assert.equal(zoom,overviewZoom);
 // De gebiedskeuze en de samenvatting horen bij dezelfde groep.
 assert.equal(q('.area-setup').nextElementSibling,q('.map-pane'));
 assert.equal(q('.area-toolbar').parentElement,q('.area-setup'));
 assert.equal(q('#rm-custom-menu').parentElement,q('.area-setup'));
 assert.equal(q('.map').nextElementSibling,q('.map-footer'));
 assert.equal(q('#rm-background').parentElement,q('.map'));
 assert.equal(q('.map-controls').parentElement,q('.map'));
 assert.equal(q('.area-summary').parentElement,q('.area-setup'));
 q('#rm-choose-area').click();assert(!areaPopovers.get('choose').hidden);
 q('#rm-custom-area').click();assert(areaPopovers.get('choose').hidden);
 assert(!areaPopovers.get('custom').hidden);
 const customTrigger=q('#rm-custom-area');
 customTrigger.click();assert(areaPopovers.get('custom').hidden);
 customTrigger.click();assert(!areaPopovers.get('custom').hidden);
 q('[data-area-mode="bounds"]').click();assert(!areaPopovers.get('bounds').hidden);
 customTrigger.click();assert(areaPopovers.get('bounds').hidden);assert(areaPopovers.get('custom').hidden);
 assert.equal(customTrigger.getAttribute('aria-expanded'),'false');
 customTrigger.click();assert(!areaPopovers.get('custom').hidden);
 assert.equal(q('.custom-choices').children.length,3);
 for(const icon of root.querySelectorAll('.custom-choices svg')){
  assert.equal(window.getComputedStyle(icon).position,'static','Tekenicoontjes blijven in hun knop');
  assert.equal(window.getComputedStyle(icon).height,'26px');
 }
 // Een lange selectie opent bij de gebiedskeuze.
 const detail=q('#rm-selection-detail');
 Object.defineProperty(detail,'scrollWidth',{configurable:true,value:600});
 Object.defineProperty(detail,'clientWidth',{configurable:true,value:300});
 updateSelectionDetails();assert(!selectionToggle.hidden);
 selectionToggle.click();assert(!selectionPopup.hidden);
 assert.equal(selectionPopup.parentElement,q('.area-setup'));assert(areaPopovers.get('custom').hidden);
 closeSelectionPopup();q('#rm-custom-area').click();
 assert(!q('[data-area-mode="bounds"]').textContent.includes('XY'));
 root.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 assert(areaPopovers.get('custom').hidden);
 q('#rm-choose-area').click();q('[name="area-kind"][value="country"]').click();
 assert.equal(mode,'country');assert(areaPopovers.get('choose').hidden);
 q('#rm-choose-area').click();q('[name="area-kind"][value="authorities"]').click();
 assert(!popup.hidden);assert(!areaPopovers.get('choose').hidden);
 // De hele gebiedskeuze is één venster: aanwijzen of binnenin klikken sluit niets.
 picker.dispatchEvent(new MouseEvent('mouseleave'));
 await new Promise(resolve=>setTimeout(resolve,250));
 assert(!popup.hidden,'Waterschappen blijven open als de muis de lijst verlaat');
 q('#rm-area-menu header').dispatchEvent(new MouseEvent('pointerdown',{bubbles:true}));
 assert(!popup.hidden,'Een klik binnen het keuzevenster sluit de lijst niet');
 q('#rm-area-menu [data-close-area]').focus();
 picker.dispatchEvent(new FocusEvent('focusout',{bubbles:true}));await settle();
 assert(!popup.hidden,'Focus op een ander onderdeel van het venster sluit de lijst niet');
 const previouslySelected=selected.has('38');
 q('#rm-list input[value="38"]').click();
 assert.equal(selected.has('38'),!previouslySelected);assert(!popup.hidden);
 q('#rm-list input[value="38"]').click();
 q('#rm-area-menu [data-close-area]').click();
 assert(popup.hidden);assert(areaPopovers.get('choose').hidden);
 q('#rm-choose-area').click();q('#rm-picker').click();
 q('.form').dispatchEvent(new MouseEvent('pointerdown',{bubbles:true}));
 assert(popup.hidden);assert(areaPopovers.get('choose').hidden);
 q('#rm-choose-area').click();q('#rm-picker').click();
 q('#rm-list input').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 assert(popup.hidden);assert(areaPopovers.get('choose').hidden);
 function modeChange(value){q('#rm-mode').value=value;q('#rm-mode').dispatchEvent(new Event('change',{bubbles:true}));}
 modeChange('country');assert.equal(collectValues().mode,'country');assert(country.classList.contains('selected'));
 setZoom(42,[211,260]);
 const previousView=JSON.stringify(viewCenter);
 for(const nextMode of ['file','draw','bounds','authorities']){
  modeChange(nextMode);await settle();
  assert.equal(zoom,42,'Gebiedskeuze moet de zoom behouden');
  assert.equal(JSON.stringify(viewCenter),previousView,'Gebiedskeuze moet de kaartpositie behouden');
 }
 modeChange('file');
 assert(q('#rm-file-demo svg'),'Bestandsknop heeft een mapicoon');
 assert.equal(q('#rm-file-demo').getAttribute('aria-label'),'Bestand openen');
 q('#rm-file-demo').click();await settle();
 assert.equal(q('#rm-file-demo').getAttribute('aria-label'),'Ander bestand openen');
 assert.equal(q('#rm-file-name').textContent,'gebieden.gpkg');
 assert.equal(q('#rm-file-path').textContent,filePath);
 q('#rm-file-location').open=true;
 assert(!q('#rm-file-demo').disabled,'Een uitgeklapt pad mag bestandskeuze niet blokkeren');
 assert.equal(q('#rm-file-layer').options.length,3);assert(!fileFeature);assert(!areaPopovers.get('file').hidden);
 assert.equal(window.requests.filter(r=>r.action==='polygon_layer').length,0);
 const choicesBefore=window.requests.filter(r=>r.action==='polygon_file').length;
 q('#rm-file-demo').click();await settle();
 assert.equal(window.requests.filter(r=>r.action==='polygon_file').length,choicesBefore+1);
 window.deferLayer=true;q('#rm-file-layer').value='west';q('#rm-file-layer').dispatchEvent(new Event('change',{bubbles:true}));await settle();
 optionButtons.get('dem').click();
 const fileOption=root.querySelector('[data-layer="dem"][data-kind="directory"], [data-layer="dem"][data-kind="file"]');
 fileOption.closest('label').querySelector('.option-actions button').click();await settle();
 assert(window.requests.some(r=>r.action==='browse'),'Bestandsknoppen blijven werken tijdens laden');
 window.pickPath='D:/ander.gpkg';q('#rm-file-demo').click();await settle();
 assert.equal(filePath,'D:/ander.gpkg');assert(!fileFeature);
 assert.equal(q('#rm-file-name').textContent,'ander.gpkg');assert(!q('#rm-file-location').open);
 window.finishLayer();await settle();assert(!fileFeature,'Een oude laag mag een nieuwe bestandskeuze niet overschrijven');
 closeOptions();
 window.rejectLayer=true;
 q('#rm-file-layer').value='west';q('#rm-file-layer').dispatchEvent(new Event('change',{bubbles:true}));await settle();
 assert(q('#rm-message').textContent.includes('geldige polygonen'));
 assert(!fileFeature);
 closeAreaPopovers();q('#rm-custom-area').click();q('[data-area-mode="file"]').click();
 assert(!areaPopovers.get('file').hidden,'Bestand wijzigen blijft opnieuw bereikbaar');
 assert(!q('#rm-file-demo').disabled);
 window.pickPath='D:/herstel.gpkg';q('#rm-file-demo').click();await settle();
 assert.equal(filePath,'D:/herstel.gpkg');assert.equal(fileLayer,'');
 assert(q('#rm-message').hidden,'Een vorige fout verdwijnt bij een nieuwe bestandskeuze');
 q('#rm-file-layer').value='oost';q('#rm-file-layer').dispatchEvent(new Event('change',{bubbles:true}));await settle();
 assert.equal(collectValues().area_layer,'oost');assert(drawing.querySelector('path'));
 assert.equal(drawing.querySelectorAll('.selection-color').length,1,'Bestandsgebied krijgt dezelfde gele selectierand als andere gebieden');
 assert(q('#rm-selection-detail').textContent.includes('Alle polygonen'));

 modeChange('draw');
 for(const [x,y] of [[190,250],[230,250],[230,290],[190,290]]){q('#rm-map').dispatchEvent(new MouseEvent('click',{clientX:x,clientY:y,bubbles:true}));}
 assert.equal(points.length,4);
 const pointZoom=zoom;
 for(const factor of [1,100,4000]){
  setZoom(factor);
  const vertex=drawing.querySelector('.point');
  const scale=Math.hypot(drawing.getScreenCTM().a,drawing.getScreenCTM().b);
  assert(Math.abs(Number(vertex.getAttribute('r'))*scale-3.5)<1e-9);
  assert.equal(window.getComputedStyle(vertex).getPropertyValue('vector-effect'),'non-scaling-stroke');
 }
 setZoom(pointZoom);
 closeDrawing.click();assert(finished);
 assert.throws(()=>collectValues(),/sla hem eerst op/i);
 saveDrawing.click();await settle();assert(drawingIsSaved());
 assert(q('#rm-message').hidden,'De kaart bevestigt het opgeslagen gebied zonder melding over de knoppen');
 assert(q('#rm-selection-detail').textContent.includes('eigen-gebied.gpkg'));
 assert(drawingToolbar.hidden);assert(!drawingToolsToggle.hidden);
 drawingToolsToggle.click();assert(!drawingToolbar.hidden);
 drawingToolsToggle.click();assert(drawingToolbar.hidden);
 drawingToolsToggle.click();assert(!drawingToolbar.hidden);
 customTrigger.click();assert(drawingToolbar.hidden);assert(areaPopovers.get('custom').hidden);
 assert(drawingIsSaved());
 customTrigger.click();assert(!areaPopovers.get('custom').hidden);
 customTrigger.click();assert(areaPopovers.get('custom').hidden);
 const polygonPoints=JSON.stringify(points);
 const expectedPolygonCenter=[0,1].map(axis=>{
  const values=points.map(point=>point[axis]);
  return (Math.min(...values)+Math.max(...values))/2;
 });
 customTrigger.click();
 q('[data-area-mode="bounds"]').click();
 useBounds.click();await settle();
 assert(mode==='bounds' && boundsFeature);
 const rectangleCenter=[...viewCenter];
 customTrigger.click();
 q('[data-area-mode="draw"]').click();
 assert(mode==='draw' && drawingIsSaved());
 assert.equal(JSON.stringify(points),polygonPoints);
 selectionToggle.click();assert(!selectionPopup.hidden);
 assert.notDeepEqual(viewCenter,rectangleCenter,'Bekijk selectie moet van de rechthoek terugzoomen naar de polygoon');
 assert.deepEqual(viewCenter,expectedPolygonCenter);
 selectionToggle.click();assert(selectionPopup.hidden);
 assert.deepEqual(viewCenter,expectedPolygonCenter);
 drawingToolsToggle.click();assert(!drawingToolbar.hidden);
 assert.equal(collectValues().area_file,'D:\\\\eigen-gebied.gpkg');
 const drawingRequest=window.requests.find(r=>r.action==='draw_save');
 assert(drawingRequest.values.coordinates.every(([x,y])=>x>3&&x<8&&y>50&&y<54));
 undoDrawing.click();assert(!drawingIsSaved());
 // Alleen polygoon tekenen; een rechthoek blijft via co?rdinaten beschikbaar.
 assert.equal(q('[data-shape="rectangle"]'),null);
 assert(q('[data-shape="polygon"]'));
 assert(q('[data-area-mode="bounds"]'));
 modeChange('authorities');assert(drawingToolbar.hidden);
 q('#rm-save').click();await settle();assert.equal(window.requests.filter(r=>r.action==='save').at(-1).values.start,false);
 q('#rm-start').click();await settle();assert.equal(window.requests.filter(r=>r.action==='save').at(-1).values.start,true);
 const runNotice=q('#rm-message');
 assert(runNotice.classList.contains('toast-success') && runNotice.classList.contains('toast-anchored'));
 assert.equal(runNotice.querySelector('strong').textContent,'Opgeslagen en gestart');
 assert.equal(runNotice.querySelector('.toast-detail').textContent,'proef.bat');
 assert(!runNotice.querySelector('button'),'Een bevestiging verdwijnt vanzelf');
 q('#rm-load').click();await settle();assert.equal(q('#rm-run-name').value,'aa-en-maas');assert.equal(selected.size,1);assert(selected.has('38'));
 assert(runNotice.hidden,'De gewijzigde velden bevestigen dat de run geladen is');
 assert(q('#rm-list input[value="38"]').checked);assert.equal(q('#rm-run-mode').value,'overwrite');
 assert(landuseStatus.hidden);
 window.loadedRun={mode:'authorities',authorities:['38'],layers:['dem'],run_id:'met-bron',workers:8,run_mode:'resume',extra_options:[{layer:'dem',flag:'landuse-run',value:'D:/afgerond'}]};
 q('#rm-load').click();await settle();
 assert.equal(landuseMode.value,'manual');assert(!landuseField.closest('label').hidden);
 assert.equal(landuseField.value,'D:/afgerond');
 assert(collectValues().extra_options.some(o=>o.flag==='landuse-run'&&o.value==='D:/afgerond'));
 window.loadedRun={...window.loadedRun,extra_options:[]};
 q('#rm-load').click();await settle();
 assert.equal(landuseMode.value,'auto');assert(landuseField.disabled);
 const duiker=q('[data-flag="duiker-tolerance"]');
 const rekeninstellingen=duiker.closest('details');
 const bronnen=q('[data-flag="rijkswateren-url"]').closest('details');
 assert(!rekeninstellingen.open && !bronnen.open);
 window.loadedRun={...window.loadedRun,layers:['afwateringseenheden'],
   extra_options:[{layer:'afwateringseenheden',flag:'duiker-tolerance',value:'2'}]};
 q('#rm-load').click();await settle();
 assert(rekeninstellingen.open && !bronnen.open);
 rekeninstellingen.querySelector('summary').click();
 assert(!rekeninstellingen.open);
 assert(collectValues().extra_options.some(o=>o.flag==='duiker-tolerance'&&o.value==='2'));
 setZoom(234);modeChange('bounds');await settle();assert.equal(zoom,234);useBounds.click();await settle();assert(boundsFeature);assert.equal(collectValues().bounds.length,4);
 const first=q('.bounds-fields input');first.value='105100';first.dispatchEvent(new Event('input',{bubbles:true}));
 assert.throws(()=>collectValues(),/Gebied gebruiken/);useBounds.click();await settle();assert(collectValues().bounds.includes('105100'));
 window.result='Geslaagd: selectie, extra opties, run laden, commando, opslaan/starten, tekenen, GPKG-laag, rechthoek en diep zoomen';
`;
(async()=>{
 try{await window.eval('(async()=>{'+script+'\n'+checks+'})()');console.log(window.result);}
 finally{window.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
