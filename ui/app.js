let catalogue;
let editType = null;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(message){const el=$('#toast');el.textContent=message;el.style.display='block';clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.style.display='none',4000)}
function find(key,id){return catalogue[key].find(x=>x.id===id)}
async function load(){const r=await fetch('/api/catalogue');catalogue=await r.json();render()}
async function save(silent=false){try{const r=await fetch('/api/catalogue',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(catalogue)});const data=await r.json();if(!r.ok){toast(data.error||'Save failed');return false}catalogue=data;render();if(!silent)toast('Catalogue saved');return true}catch(error){toast(error.message||'Save failed');return false}}
async function changeLifecycle(id,action){
 if(!await save(true))return;
 try{
  const r=await fetch(`/api/catalogue/offerings/${encodeURIComponent(id)}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:catalogue.version})});
  const data=await r.json();if(!r.ok)throw new Error(data.error||'Lifecycle change failed');
  catalogue=data;render();toast(action==='publish'?'Published. Available in CPQ now.':'Retired. Removed from new CPQ selections.');
 }catch(error){toast(error.message||'Lifecycle change failed')}
}
function render(){
 $('#version').textContent=catalogue.version;
 $('#specs').innerHTML=catalogue.productSpecifications.map(s=>{
   const chips=s.isBundle?s.bundledProductSpecification.map(ref=>{const child=find('productSpecifications',ref.id);return `<span class="chip">${esc(child?.name||ref.id)} <input class="allowance" type="number" min="0.01" step="any" value="${esc(ref.value)}" data-value="${esc(s.id)}:${esc(ref.id)}" title="Allowance"> ${esc(child?.unit||'')}<button data-remove="${esc(s.id)}:${esc(ref.id)}" title="Remove link">×</button></span>`}).join(''):'';
   const drop=s.isBundle?`<div class="dropzone filled" data-drop="ps:${esc(s.id)}">${chips||'Drop product specifications here'}</div>`:'';
   return `<div class="card" ${s.isBundle?'':'draggable="true" data-drag="ps:'+esc(s.id)+'"'}><div class="card-top"><div><div class="card-title">${esc(s.name)}</div><div class="card-id">${esc(s.id)}</div></div><span class="tag ${s.isBundle?'orange':'green'}">${s.isBundle?'COMPOSITE PS':'LEAF PS'}</span></div>${!s.isBundle?`<div class="card-meta"><span class="chip">${esc(s.characteristic)}</span><span class="chip">${esc(s.unit)}</span></div>`:''}${drop}</div>`
 }).join('');
 $('#offers').innerHTML=catalogue.productOfferings.map(o=>`<div class="card"><div class="card-top"><div><div class="card-title">${esc(o.name)}</div><div class="card-id">${esc(o.id)}</div></div><span class="tag ${o.lifecycleStatus==='Active'?'green':'orange'}">${esc(o.lifecycleStatus)}</span></div><div class="card-meta"><span class="chip">${esc(find('productSpecifications',o.productSpecification.id)?.name||o.productSpecification.id)}</span>${o.allowedSegments.map(x=>`<span class="chip">${esc(x)}</span>`).join('')}</div><div class="offer-price">£${esc(o.monthlyPrice)} <small>/ month</small></div><div class="card-actions">${o.lifecycleStatus==='Retired'?'<span class="form-hint">No longer sold</span>':`<button data-lifecycle="${esc(o.id)}" data-action="${o.lifecycleStatus==='Draft'?'publish':'retire'}">${o.lifecycleStatus==='Draft'?'Publish offer':'Retire offer'}</button>`}</div></div>`).join('');
 $('#request-offer').innerHTML=catalogue.productOfferings.filter(o=>o.lifecycleStatus==='Active').map(o=>`<option value="${esc(o.id)}">${esc(o.name)} · £${esc(o.monthlyPrice)}/month</option>`).join('');
}
function openEditor(type){editType=type;const fields={cfs:[['id','ID','cfs-new'],['name','Service name','New CFS'],['targetSystem','Target system','UDM / HSS'],['operation','Proposed operation','setAllowance'],['unit','Unit','GB']],ps:[['id','ID','ps-new'],['name','Specification name','New allowance'],['characteristic','Characteristic key','allowance'],['unit','Unit','GB']],bundle:[['id','ID','ps-bundle-new'],['name','Composite name','New composite specification']],po:[['id','ID','po-new'],['name','Offering name','New offer'],['monthlyPrice','Monthly price GBP','10.00'],['setupPrice','Setup price GBP','0.00']]};const titles={cfs:'Customer Facing Service',ps:'Leaf Product Specification',bundle:'Composite Product Specification',po:'Product Offering'};$('#editor-type').textContent='CREATE ENTITY';$('#editor-title').textContent=titles[type];$('#editor-fields').innerHTML='<div class="dialog-fields">'+fields[type].map(([name,label,placeholder])=>`<label>${label}<input name="${name}" placeholder="${placeholder}" required></label>`).join('')+(type==='po'?`<label>Composite specification<select name="bundleId" required>${catalogue.productSpecifications.filter(x=>x.isBundle).map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')}</select></label><label>Customer segment<select name="segment"><option value="consumer,business">Consumer and business</option><option value="consumer">Consumer</option><option value="business">Business</option></select></label>`:'')+'</div>';$('#editor').showModal()}
function createEntity(event){event.preventDefault();const data=Object.fromEntries(new FormData(event.target));let key,obj;if(editType==='cfs'){key='serviceSpecifications';obj={id:data.id,name:data.name,targetSystem:data.targetSystem,operation:data.operation,unit:data.unit}}else if(editType==='ps'){key='productSpecifications';obj={id:data.id,name:data.name,characteristic:data.characteristic,unit:data.unit,serviceSpecificationIds:[...(catalogue.productSpecifications.find(x=>!x.isBundle&&x.characteristic===data.characteristic)?.serviceSpecificationIds||[])]}}else if(editType==='bundle'){key='productSpecifications';obj={id:data.id,name:data.name,isBundle:true,bundledProductSpecification:[]}}else{key='productOfferings';obj={id:data.id,name:data.name,lifecycleStatus:'Draft',monthlyPrice:data.monthlyPrice,setupPrice:data.setupPrice,allowedSegments:data.segment.split(','),productSpecification:{id:data.bundleId}}}if(find(key,data.id)){toast('That ID already exists');return}catalogue[key].push(obj);$('#editor').close();render();toast('Created as draft. Combine specifications and save.')}
document.addEventListener('dragstart',e=>{const card=e.target.closest('[data-drag]');if(card)e.dataTransfer.setData('text/plain',card.dataset.drag)});
document.addEventListener('dragover',e=>{const zone=e.target.closest('[data-drop]');if(zone){e.preventDefault();zone.classList.add('over')}});
document.addEventListener('dragleave',e=>{const zone=e.target.closest('[data-drop]');if(zone)zone.classList.remove('over')});
document.addEventListener('drop',e=>{const zone=e.target.closest('[data-drop]');if(!zone)return;e.preventDefault();zone.classList.remove('over');const [sourceType,sourceId]=e.dataTransfer.getData('text/plain').split(':'),[targetType,targetId]=zone.dataset.drop.split(':');if(sourceType!==targetType){toast('This card belongs in another catalogue layer');return}const target=find('productSpecifications',targetId);if(targetType==='cfs'){if(!target.serviceSpecificationIds.includes(sourceId))target.serviceSpecificationIds.push(sourceId)}else{if(sourceId===targetId){toast('A specification cannot include itself');return}if(!target.bundledProductSpecification.some(x=>x.id===sourceId))target.bundledProductSpecification.push({id:sourceId,value:1})}render();toast('Link added. Set the allowance and save.')});
document.addEventListener('click',e=>{const remove=e.target.closest('[data-remove]');if(remove){const [parent,id]=remove.dataset.remove.split(':'),spec=find('productSpecifications',parent);if(spec.isBundle)spec.bundledProductSpecification=spec.bundledProductSpecification.filter(x=>x.id!==id);else spec.serviceSpecificationIds=spec.serviceSpecificationIds.filter(x=>x!==id);render()}const life=e.target.closest('[data-lifecycle]');if(life){life.disabled=true;changeLifecycle(life.dataset.lifecycle,life.dataset.action).finally(()=>{life.disabled=false})}});
document.addEventListener('change',e=>{if(e.target.matches('[data-value]')){const [parent,id]=e.target.dataset.value.split(':');const ref=find('productSpecifications',parent).bundledProductSpecification.find(x=>x.id===id);ref.value=Number(e.target.value)}});
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.nav').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('.view').forEach(x=>x.classList.add('hidden'));$('#'+b.dataset.view+'-view').classList.remove('hidden')}));
$('#save').addEventListener('click',()=>save());$('#new-ps').onclick=()=>openEditor('ps');$('#new-bundle').onclick=()=>openEditor('bundle');$('#new-po').onclick=()=>openEditor('po');$('#editor-form').addEventListener('submit',createEntity);$('#close-editor').onclick=$('#cancel-editor').onclick=()=>$('#editor').close();
$('#request-form').addEventListener('submit',async e=>{
 e.preventDefault();
 try{
  await window.businessRulesReady;
  const form=new FormData(e.target),body={...Object.fromEntries(form),exceptionRequested:form.has('exceptionRequested'),context:window.collectRuleContext()};
  const gemini=e.submitter?.value==='gemini';
  const endpoint=gemini?'/api/agent/requests':'/api/preview';
  let r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),x=await r.json();
  if(!r.ok){$('#result').innerHTML=`<h2>Quote needs attention</h2><p role="alert">${esc(x.error||'Preview failed')}</p>`;return}
  if(gemini){
   $('#result').innerHTML='<h2>Gemini is selecting an offer</h2><p>The cloud agent is processing your request. Pricing will be validated by code.</p>';
   for(let attempt=0;attempt<40;attempt++){
    await new Promise(resolve=>setTimeout(resolve,3000));
    r=await fetch(`/api/agent/results/${encodeURIComponent(x.requestId)}`);x=await r.json();
    if(r.status!==202)break;
   }
   if(r.status===202){$('#result').innerHTML='<h2>Still processing</h2><p>Refresh the request later or try again.</p>';return}
   if(!r.ok || !x.quote){$('#result').innerHTML=`<h2>Quote needs attention</h2><p role="alert">${esc(x.error||'Cloud request failed')}</p>`;return}
  }
  const recurring=x.quote.quoteTotalPrice[0].price.dutyFreeAmount.value;
  $('#result').innerHTML=`<div class="result-summary"><h2>Quote preview</h2><span class="result-status">${esc(x.status)}</span></div><div class="result-section"><h3>Product offer</h3>${x.quote.quoteItem.map(i=>`<div class="result-item"><strong>${esc(i.productOffering.name)}</strong><small>${i.product.productCharacteristic.map(c=>`${esc(c.value)} ${esc(c.unit)} ${esc(c.name)}`).join(' · ')}</small><small>Base £${esc(i.pricingDecision.baseMonthlyPrice)} · Discount ${esc(i.pricingDecision.discountPercent)}%</small></div>`).join('')}<div class="result-line"><span>Monthly, before tax${x.approval.required?' — subject to approval':''}</span><strong>£${esc(recurring)}</strong></div></div><div class="result-section"><h3>Rules applied</h3>${x.ruleDecisions.map(d=>`<div class="result-item"><strong>${esc(d.kind)} · ${esc(d.rowId)}</strong><small>${esc(d.reason)}</small></div>`).join('')}<p class="form-hint">Rule version ${esc(x.rulesVersion)}</p></div><p class="form-hint">${gemini?'Gemini proposed the offer; code validated the quote.':'Manual offer preview.'} No network provisioning has occurred.</p>`;
 }catch(error){toast(error.message||'Could not preview quote')}
});
load().catch(()=>toast('Could not load catalogue'));
