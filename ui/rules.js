let businessRules;
let activeRuleKind = 'price';
let ruleEditorState;
const ruleLabels = {price:'Prices',eligibility:'Eligibility',discount:'Discounts',approval:'Approvals'};
const operatorLabels = {eq:'equals',ne:'does not equal',in:'is in',notIn:'is not in',gt:'greater than',gte:'at least',lt:'less than',lte:'at most',exists:'has a value'};
const ruleTable = kind => businessRules.tables.find(t => t.kind === kind);
const columnById = id => businessRules.columns.find(c => c.id === id);
const isContextColumn = c => c.source.startsWith('request.context.');
function outcomeText(kind,outcome){
  if(kind==='eligibility')return outcome.eligible?'Eligible':'Ineligible';
  if(kind==='approval')return {approve:'Proceed',review:'Human approval',reject:'Reject'}[outcome.decision];
  if(kind==='discount')return `${typeof outcome.discountPercent==='object'?'Column value':outcome.discountPercent}% discount`;
  const show=v=>typeof v==='object'?columnById(v.column)?.label||v.column:`£${v}`;
  return `${show(outcome.monthlyPrice)} / month · ${show(outcome.setupPrice)} setup`;
}
function conditionText(c,extraColumns=[]){
  const label=id=>(columnById(id)||extraColumns.find(x=>x.id===id))?.label||id;
  return `${label(c.column)} ${operatorLabels[c.operator]} ${c.valueFrom?label(c.valueFrom):Array.isArray(c.value)?c.value.join(', '):String(c.value)}`;
}
async function loadBusinessRules(){
  const response=await fetch('/api/rules');
  if(!response.ok)throw new Error('Could not load business rules');
  businessRules=await response.json();renderBusinessRules();
}
function renderBusinessRules(){
  $('#rules-version').textContent=businessRules.version;
  $('#rule-tabs').innerHTML=Object.keys(ruleLabels).map(kind=>`<button type="button" role="tab" aria-selected="${kind===activeRuleKind}" data-rule-tab="${kind}" class="${kind===activeRuleKind?'selected':''}">${ruleLabels[kind]}</button>`).join('');
  const table=ruleTable(activeRuleKind);
  $('#rule-table-panel').innerHTML=`<div class="rule-panel-heading"><h2>${esc(table.name)}</h2><button type="button" class="primary" id="add-rule-row">Add row</button></div><div class="table-scroll"><table class="decision-table"><thead><tr><th>Rule</th><th>Priority</th><th>All conditions</th><th>Outcome</th><th>Effective dates</th><th>Actions</th></tr></thead><tbody>${[...table.rows].sort((a,b)=>b.priority-a.priority).map(r=>`<tr><td><strong>${esc(r.id)}</strong><small>${r.enabled?'Enabled':'Disabled'} · ${esc(r.reason)}</small></td><td>${r.priority}</td><td>${r.conditions.length?r.conditions.map(c=>esc(conditionText(c))).join('<br>'):'Always'}</td><td>${esc(outcomeText(table.kind,r.outcome))}</td><td>${esc(r.effectiveFrom||'Any start')}<br>${esc(r.effectiveTo||'No end')}</td><td><button class="rule-link" type="button" data-edit-rule="${esc(r.id)}">Edit</button><button class="rule-link" type="button" data-delete-rule="${esc(r.id)}">Delete</button></td></tr>`).join('')||'<tr><td colspan="6">No conditional rows. The fallback below is used.</td></tr>'}</tbody></table></div><div class="rule-fallback"><span><strong>Fallback when no row matches</strong><br>${esc(outcomeText(table.kind,table.defaultOutcome))}</span><button type="button" class="secondary" id="edit-rule-fallback">Edit fallback</button></div>`;
  $('#column-count').textContent=`(${businessRules.columns.length})`;
  $('#rule-columns').innerHTML=`<div class="table-scroll"><table class="decision-table"><thead><tr><th>Column</th><th>Type</th><th>Input</th><th>Default</th><th></th></tr></thead><tbody>${businessRules.columns.map(c=>`<tr><td>${esc(c.label)}<small>${esc(c.id)}</small></td><td>${esc(c.type)}</td><td>${isContextColumn(c)?'Customer input':c.source.startsWith('offer.')?'Offering':c.source.startsWith('derived.')?'Calculated':'Request'}</td><td>${'default'in c?esc(Array.isArray(c.default)?c.default.join(', '):String(c.default)):'—'}</td><td>${isContextColumn(c)?`<button type="button" class="rule-link" data-edit-column="${esc(c.id)}">Edit</button><button type="button" class="rule-link" data-delete-column="${esc(c.id)}">Delete</button>`:'Built-in'}</td></tr>`).join('')}</tbody></table></div>`;
  renderContextInputs();
}
function renderContextInputs(){
  const previous=Object.fromEntries([...document.querySelectorAll('[data-context-key]')].map(e=>[e.dataset.contextKey,e.value]));
  const seen=new Set();
  $('#request-context').innerHTML=businessRules.columns.filter(isContextColumn).filter(c=>{if(seen.has(c.source))return false;seen.add(c.source);return true}).map(c=>{
    const key=c.source.split('.').at(-1),value=previous[key]??('default'in c?(Array.isArray(c.default)?c.default.join(', '):String(c.default)):'');
    return `<label>${esc(c.label)}${c.type==='boolean'?`<select data-context-key="${esc(key)}" data-context-type="boolean"><option value="">Not provided</option><option value="true" ${value==='true'?'selected':''}>Yes</option><option value="false" ${value==='false'?'selected':''}>No</option></select>`:`<input data-context-key="${esc(key)}" data-context-type="${c.type}" type="${c.type==='number'?'number':'text'}" ${c.type==='number'?'step="any"':''} value="${esc(value)}" ${c.type==='list'?'placeholder="Comma-separated values"':''}>`}</label>`;
  }).join('');
}
window.collectRuleContext=()=>Object.fromEntries([...document.querySelectorAll('[data-context-key]')].filter(e=>e.value.trim()!=='').map(e=>[e.dataset.contextKey,e.dataset.contextType==='boolean'?e.value==='true':e.dataset.contextType==='list'?e.value.split(',').map(v=>v.trim()):e.value]));
function outcomeFields(kind,outcome){
  if(kind==='eligibility')return `<label>Eligibility<select name="eligible"><option value="true" ${outcome.eligible?'selected':''}>Eligible</option><option value="false" ${!outcome.eligible?'selected':''}>Ineligible</option></select></label>`;
  if(kind==='approval')return `<label>Decision<select name="decision">${[['approve','Proceed'],['review','Human approval required'],['reject','Reject']].map(([value,label])=>`<option value="${value}" ${outcome.decision===value?'selected':''}>${label}</option>`).join('')}</select></label>`;
  if(kind==='discount')return `<label>Discount %<input name="discountPercent" type="number" min="0" max="100" step="0.01" value="${esc(typeof outcome.discountPercent==='object'?'':outcome.discountPercent)}" required></label>`;
  return ['monthlyPrice','setupPrice'].map(key=>`<label>${key==='monthlyPrice'?'Monthly price':'Setup price'} GBP<input name="${key}" type="number" min="0" max="1000000" step="0.01" value="${esc(typeof outcome[key]==='object'?'':outcome[key])}" placeholder="Use offering price when blank"></label>`).join('');
}
function readOutcome(kind,form){
  if(kind==='eligibility')return {eligible:form.get('eligible')==='true'};
  if(kind==='approval')return {decision:form.get('decision')};
  if(kind==='discount')return {discountPercent:form.get('discountPercent')};
  return Object.fromEntries(['monthlyPrice','setupPrice'].map(key=>[key,form.get(key)===''?{column:key==='monthlyPrice'?'baseMonthlyPrice':'baseSetupPrice'}:form.get(key)]));
}
function columnOptions(value){return businessRules.columns.filter(c=>activeRuleKind==='approval'||!c.source.startsWith('derived.')).map(c=>`<option value="${esc(c.id)}" ${c.id===value?'selected':''}>${esc(c.label)}</option>`).join('')}
function addConditionField(condition={column:'offerId',operator:'eq',value:''}){
  const row=document.createElement('div');row.className='condition-editor';
  row.innerHTML=`<label>Column<select data-condition-column>${columnOptions(condition.column)}</select></label><label>Compare<select data-condition-operator>${Object.entries(operatorLabels).map(([value,label])=>`<option value="${value}" ${condition.operator===value?'selected':''}>${label}</option>`).join('')}</select></label><label>Compare with<select data-condition-mode><option value="literal">Value</option><option value="column" ${condition.valueFrom?'selected':''}>Another column</option></select></label><label>Value<input data-condition-value value="${esc(Array.isArray(condition.value)?condition.value.join(', '):condition.value??'')}" placeholder="Use commas for a list"></label><label>Other column<select data-condition-from>${columnOptions(condition.valueFrom)}</select></label><button type="button" class="rule-link" data-remove-condition>Remove</button>`;
  const update=()=>{const byColumn=row.querySelector('[data-condition-mode]').value==='column';row.querySelector('[data-condition-value]').parentElement.hidden=byColumn;row.querySelector('[data-condition-from]').parentElement.hidden=!byColumn};
  row.querySelector('[data-condition-mode]').onchange=update;update();$('#condition-list').append(row);
}
function showRuleEditor(mode,id){
  const table=ruleTable(activeRuleKind),existing=table.rows.find(r=>r.id===id);
  ruleEditorState={mode,id,kind:activeRuleKind};$('#rule-editor-error').textContent='';
  $('#rule-editor-title').textContent=mode==='fallback'?`${table.name}: fallback`:existing?'Edit rule':'Add rule';
  if(mode==='fallback')$('#rule-editor-fields').innerHTML=outcomeFields(table.kind,table.defaultOutcome);
  else{
    const row=existing||{id:`rule-${Date.now()}`,priority:100,enabled:true,conditions:[],outcome:table.defaultOutcome,reason:''};
    $('#rule-editor-fields').innerHTML=`<label>Rule ID<input name="id" value="${esc(row.id)}" required></label><label>Priority — larger number wins<input name="priority" type="number" min="0" max="1000000" value="${row.priority}" required></label><label class="check-label"><input name="enabled" type="checkbox" ${row.enabled?'checked':''}> Enabled</label><div id="condition-list"></div><button type="button" class="secondary" id="add-condition">Add condition</button><p class="form-hint">An empty condition list matches every request. All conditions on this row must match.</p>${outcomeFields(table.kind,row.outcome)}<label>Valid from — UTC date or timestamp<input name="effectiveFrom" value="${esc(row.effectiveFrom||'')}" placeholder="2027-04-01"></label><label>Valid until — exclusive, UTC<input name="effectiveTo" value="${esc(row.effectiveTo||'')}" placeholder="2028-04-01"></label><label>Explanation<textarea name="reason" rows="2" required>${esc(row.reason)}</textarea></label>`;
    row.conditions.forEach(addConditionField);$('#add-condition').onclick=()=>addConditionField();
  }
  $('#rule-editor').showModal();
}
function showColumnEditor(id){
  const c=columnById(id)||{id:'',label:'',type:'string',source:'request.context.'};ruleEditorState={mode:'column',id};
  $('#rule-editor-title').textContent=id?'Edit input column':'Add input column';$('#rule-editor-error').textContent='';
  $('#rule-editor-fields').innerHTML=`<label>Column key<input name="id" value="${esc(c.id)}" placeholder="contractMonths" pattern="[A-Za-z][A-Za-z0-9_]{0,63}" required ${id?'readonly':''}></label><label>Display name<input name="label" value="${esc(c.label)}" placeholder="Contract months" required></label><label>Value type<select name="type">${['string','number','boolean','list'].map(t=>`<option value="${t}" ${t===c.type?'selected':''}>${t}</option>`).join('')}</select></label><label>Customer input key<input name="key" value="${esc(c.source.split('.').at(-1))}" placeholder="contractMonths" pattern="[A-Za-z][A-Za-z0-9_]*" required></label><label class="check-label"><input name="hasDefault" type="checkbox" ${'default'in c?'checked':''}> Use a default when missing</label><label>Default value<input name="default" value="${esc('default'in c?(Array.isArray(c.default)?c.default.join(', '):String(c.default)):'')}" placeholder="24"></label>`;
  $('#rule-editor').showModal();
}
function parseLiteral(value,type){
  if(type==='boolean'){if(!['true','false'].includes(value))throw new Error('Use true or false for a boolean value');return value==='true'}
  if(type==='number'){if(value.trim()===''||!Number.isFinite(Number(value)))throw new Error('Enter a valid number');return value}
  if(type==='list')return value.split(',').map(s=>s.trim()).filter(Boolean);
  return value;
}
$('#rule-editor-form').onsubmit=event=>{
  event.preventDefault();const form=new FormData(event.target);
  try{
    if(ruleEditorState.mode==='column'){
      const column={id:form.get('id'),label:form.get('label'),type:form.get('type'),source:`request.context.${form.get('key')}`};
      if(form.has('hasDefault'))column.default=parseLiteral(form.get('default'),column.type);
      if(!ruleEditorState.id&&columnById(column.id))throw new Error('That column key already exists');
      if(ruleEditorState.id)businessRules.columns[businessRules.columns.findIndex(c=>c.id===ruleEditorState.id)]=column;else businessRules.columns.push(column);
    }else{
      const table=ruleTable(ruleEditorState.kind),outcome=readOutcome(table.kind,form);
      if(ruleEditorState.mode==='fallback')table.defaultOutcome=outcome;
      else{
        const conditions=[...document.querySelectorAll('.condition-editor')].map(el=>{
          const column=el.querySelector('[data-condition-column]').value,operator=el.querySelector('[data-condition-operator]').value;
          return {column,operator,...(el.querySelector('[data-condition-mode]').value==='column'?{valueFrom:el.querySelector('[data-condition-from]').value}:{value:parseLiteral(el.querySelector('[data-condition-value]').value,operator==='exists'?'boolean':['in','notIn'].includes(operator)?'list':columnById(column).type)})};
        });
        const row={id:form.get('id'),enabled:form.has('enabled'),priority:Number(form.get('priority')),conditions,outcome,reason:form.get('reason')};
        for(const key of ['effectiveFrom','effectiveTo'])if(form.get(key))row[key]=form.get(key);
        if(table.rows.some(r=>r.id===row.id&&r.id!==ruleEditorState.id))throw new Error('That rule ID already exists');
        if(ruleEditorState.id)table.rows[table.rows.findIndex(r=>r.id===ruleEditorState.id)]=row;else table.rows.push(row);
      }
    }
    $('#rule-editor').close();renderBusinessRules();toast('Changes kept. Save rules to apply them.');
  }catch(error){$('#rule-editor-error').textContent=error.message}
};
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.ruleTab){activeRuleKind=button.dataset.ruleTab;renderBusinessRules()}
  if(button.id==='add-rule-row')showRuleEditor('row');
  if(button.id==='edit-rule-fallback')showRuleEditor('fallback');
  if(button.dataset.editRule)showRuleEditor('row',button.dataset.editRule);
  if(button.dataset.deleteRule){ruleTable(activeRuleKind).rows=ruleTable(activeRuleKind).rows.filter(r=>r.id!==button.dataset.deleteRule);renderBusinessRules();toast('Row removed. Save rules to apply.')}
  if(button.hasAttribute('data-remove-condition'))button.closest('.condition-editor').remove();
  if(button.dataset.editColumn)showColumnEditor(button.dataset.editColumn);
  if(button.dataset.deleteColumn){businessRules.columns=businessRules.columns.filter(c=>c.id!==button.dataset.deleteColumn);renderBusinessRules();toast('Column removed. Referencing rows must be updated before saving.')}
});
$('#add-rule-column').onclick=()=>showColumnEditor();
$('#close-rule-editor').onclick=$('#cancel-rule-editor').onclick=()=>$('#rule-editor').close();
$('#save-rules').onclick=async()=>{
  try{const response=await fetch('/api/rules',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(businessRules)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Could not save rules');businessRules=result;renderBusinessRules();toast('Rules saved. The next quote uses this version.')}catch(error){toast(error.message)}
};
let ruleProposal=null;
function showRuleProposal(data){
  const review=$('#rule-assistant-review');
  if(data.preview.clarification){ruleProposal=null;review.innerHTML=`<h3>Gemini needs one more detail</h3><p>${esc(data.preview.clarification)}</p>`;review.classList.remove('hidden');return}
  ruleProposal=data.preview;const p=ruleProposal,row=p.row;
  review.innerHTML=`<h3>${esc(p.tableName)} · new row ${esc(row.id)}</h3>${p.summary?`<p>${esc(p.summary)}</p>`:''}<ul>`+
    `<li>When: ${row.conditions.length?row.conditions.map(c=>esc(conditionText(c,p.newColumns))).join(' and '):'always'}</li>`+
    `<li>Then: ${esc(outcomeText(p.table,row.outcome))}</li><li>Priority ${row.priority}${row.effectiveFrom||row.effectiveTo?` · effective ${esc(row.effectiveFrom||'any start')} to ${esc(row.effectiveTo||'no end')}`:''}</li>`+
    p.newColumns.map(c=>`<li>New customer input column: ${esc(c.label)} (${esc(c.id)}, ${esc(c.type)})</li>`).join('')+
    p.warnings.map(w=>`<li class="rule-review-warning">${esc(w)}</li>`).join('')+
    `</ul><div class="rule-review-actions"><button type="button" class="primary" id="rule-proposal-add">Add to editor</button><button type="button" class="secondary" id="rule-proposal-discard">Discard</button></div>`;
  review.classList.remove('hidden');
  $('#rule-proposal-add').onclick=()=>{
    // Merge into the page's copy so unsaved manual edits survive; Save rules validates the whole table again.
    for(const column of ruleProposal.newColumns)if(!columnById(column.id))businessRules.columns.push(column);
    const table=ruleTable(ruleProposal.table),added={...ruleProposal.row};
    while(table.rows.some(r=>r.id===added.id))added.id+='-new';
    table.rows.push(added);activeRuleKind=ruleProposal.table;
    review.classList.add('hidden');ruleProposal=null;$('#rule-assistant-text').value='';
    renderBusinessRules();toast('Rule added to the editor. Review it, then Save rules.');
  };
  $('#rule-proposal-discard').onclick=()=>{review.classList.add('hidden');ruleProposal=null};
}
$('#rule-assistant-form').onsubmit=async event=>{
  event.preventDefault();$('#rule-assistant-error').textContent='';
  const button=$('#rule-assistant-send');button.disabled=true;button.textContent='Drafting…';
  try{
    const response=await fetch('/api/rules/assistant/propose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:$('#rule-assistant-text').value,version:businessRules.version})});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Could not draft the rule');
    showRuleProposal(data);
  }catch(error){$('#rule-assistant-error').textContent=error.message}
  finally{button.disabled=false;button.textContent='Draft rule'}
};
window.attachVoiceInput({button:$('#rule-assistant-mic'),note:$('#rule-assistant-note'),target:$('#rule-assistant-text'),
  onRecording:recording=>{$('#rule-assistant-send').disabled=recording}});
window.businessRulesReady=loadBusinessRules();
window.businessRulesReady.catch(error=>toast(error.message));
