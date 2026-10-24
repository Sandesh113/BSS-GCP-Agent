let cpqOptions={offers:[],promotions:[]};
let cpqCustomer;
let cpqEmailConfig=null;
const selectedOffers=new Map();
const cardTerms=new Map();
const cpqEl=selector=>document.querySelector(selector);
const cpqEsc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pounds=value=>Number(value).toFixed(2);

function allowanceText(item){
  if(item.characteristic==='dataGb')return `${item.value} GB data`;
  if(item.characteristic==='voiceMinutes')return `${item.value} voice minutes`;
  if(item.characteristic==='smsCount')return `${item.value} texts`;
  return `${item.value} ${item.unit} ${item.name}`;
}
function termFor(offer){
  const stored=cardTerms.get(offer.id);
  return offer.terms.includes(stored)?stored:offer.terms.includes(12)?12:offer.terms[0];
}
function basePrice(offer){return Number(offer.termPrices[String(termFor(offer))]??offer.monthlyPrice)}
function activePromotion(){return cpqOptions.promotions.find(p=>p.id===cpqEl('#cpq-promotion').value)}
function displayedPrice(offer){
  const promo=activePromotion();
  return promo&&promo.offeringIds.includes(offer.id)?basePrice(offer)*(1-Number(promo.discountPercent)/100):basePrice(offer);
}
function renderPlans(){
  cpqEl('#cpq-offer-count').textContent=`${cpqOptions.offers.length} available`;
  cpqEl('#cpq-plan-grid').innerHTML=cpqOptions.offers.map(offer=>{
    const selected=selectedOffers.has(offer.id);
    const hero=offer.allowances.find(a=>a.characteristic==='dataGb')||offer.allowances[0];
    const rest=offer.allowances.filter(a=>a!==hero);
    const reduced=displayedPrice(offer)<basePrice(offer);
    return `<article class="cpq-plan-card ${selected?'selected':''}" data-offer-id="${cpqEsc(offer.id)}"><div class="cpq-plan-top"><span class="cpq-plan-kind ${offer.kind==='addOn'?'addon':''}">${offer.kind==='addOn'?'ADD-ON':'MOBILE PLAN'}</span>${selected?'<span class="cpq-chosen">✓ Selected</span>':''}</div><h3>${cpqEsc(offer.name)}</h3><div class="cpq-plan-hero">${cpqEsc(allowanceText(hero))}</div><div class="cpq-plan-allowances">${rest.map(a=>`<div>✓ ${cpqEsc(allowanceText(a))}</div>`).join('')||'<div>✓ Add to a compatible mobile plan</div>'}</div><div class="cpq-plan-bottom"><div class="cpq-plan-price">£${pounds(displayedPrice(offer))}<span>/month</span></div>${reduced?`<div class="cpq-was">£${pounds(basePrice(offer))} before promotion · approval required</div>`:'<div class="cpq-was">Illustrative price before tax</div>'}<label>Contract length<select class="cpq-card-term" data-term-id="${cpqEsc(offer.id)}">${offer.terms.map(months=>`<option value="${months}" ${months===termFor(offer)?'selected':''}>${months} months</option>`).join('')}</select></label><button type="button" class="cpq-select-button ${selected?'chosen':''}" data-toggle-offer="${cpqEsc(offer.id)}">${selected?'Remove from quote':'Select product'}</button></div></article>`;
  }).join('')||'<p>No Active offerings are available yet.</p>';
}
function renderBasket(){
  const chosen=cpqOptions.offers.filter(offer=>selectedOffers.has(offer.id));
  cpqEl('#cpq-selected-count').textContent=`${chosen.length} selected`;
  cpqEl('#cpq-basket-lines').innerHTML=chosen.length?chosen.map(offer=>`<div class="cpq-basket-line"><div><strong>${cpqEsc(offer.name)}</strong><small>${termFor(offer)} months</small></div><b>£${pounds(displayedPrice(offer))}</b></div>`).join(''):'<p class="cpq-empty-basket">Choose a product tile to begin.</p>';
  const total=chosen.reduce((sum,offer)=>sum+displayedPrice(offer),0);
  cpqEl('#cpq-estimate').innerHTML=`<span>Indicative monthly total</span><strong>£${pounds(total)}</strong><small>Before tax. Final price and compatibility are checked below.</small>`;
}
function renderPromotion(selected){
  const now=new Date();
  cpqEl('#cpq-promotion').innerHTML='<option value="">No promotion</option>'+cpqOptions.promotions.map(p=>{
    const active=new Date(p.validFrom)<=now&&now<new Date(p.validTo);
    return `<option value="${cpqEsc(p.id)}" ${selected===p.id?'selected':''} ${active?'':'disabled'}>${cpqEsc(p.name)} · ${cpqEsc(p.discountPercent)}%${active?'':' (outside offer dates)'}</option>`;
  }).join('');
  showPromotion();
}
function showPromotion(){
  const promo=activePromotion();
  cpqEl('#cpq-promotion-detail').textContent=promo?`${promo.description} Valid ${promo.validFrom} to ${promo.validTo} (end exclusive).`:'';
}
function clearQuote(){
  cpqEl('#cpq-result').innerHTML='<div class="empty-icon">◈</div><h2>Your quote will appear here</h2><p>Validate your selection to see the final price and policy checks.</p>';
}
function renderSubmittedOrder(details){
  const order=details.productOrder,service=details.serviceOrder,review=details.contractReview;
  cpqEl('#cpq-order-panel').innerHTML=`<div class="cpq-order-head"><div><div class="eyebrow">TMF622 PRODUCT ORDER</div><h3>POC order submitted</h3><p>${cpqEsc(order.id)} · ${cpqEsc(order.state)} · ${service.orderItem.length} CFS actions prepared</p></div><span class="result-status">ORDER CREATED</span></div><p class="form-hint">The service order is an orchestration payload only. No RFS or network activation is triggered.</p><div class="cpq-order-grid"><details><summary>ProductOrder JSON</summary><pre>${cpqEsc(JSON.stringify(order,null,2))}</pre></details><details><summary>PS → CFS service order JSON</summary><pre>${cpqEsc(JSON.stringify(service,null,2))}</pre></details></div><div class="cpq-contract"><h3>Draft contract summary</h3><p>The PDF lists the customer, products, allowances, terms and quoted prices. It is a POC draft because provider and regulatory disclosures are incomplete.</p><a class="secondary cpq-download" href="/api/cpq/orders/${encodeURIComponent(order.id)}/contract.pdf" download>Download draft PDF</a><details><summary>Contract verification gaps</summary><ul>${review.missingDisclosures.map(gap=>`<li>${cpqEsc(gap)}</li>`).join('')}</ul></details><form id="cpq-email-form"><div class="cpq-email-fields"><label>Primary contact email<input name="primaryEmail" type="email" value="${cpqEsc(details.customer.email)}" required></label><label>Optional copy email<input name="copyEmail" type="email" placeholder="Your email for a copy"></label></div><button class="secondary" type="submit">Email draft PDF with Google</button><p id="cpq-email-status" role="status" class="form-hint">${cpqEsc(cpqEmailConfig?.configured ? `Google sign-in will ask ${cpqEmailConfig.sender||'your mailbox'} to send this draft PDF.` : 'Google email setup is still required.')}</p></form></div>`;
  cpqEl('#cpq-order-panel').dataset.orderId=order.id;
}
async function openExistingOrderFromUrl(){
  const orderId=new URLSearchParams(window.location.search).get('order');
  if(!orderId)return;
  const response=await fetch(`/api/cpq/orders/${encodeURIComponent(orderId)}`);
  const details=await response.json();
  if(!response.ok)throw new Error(details.error||'Could not reopen order');
  document.querySelector('[data-view="cpq"]').click();
  cpqEl('#cpq-result').innerHTML='<h2>Submitted order</h2><p class="form-hint">This saved POC order can be reviewed and its draft contract emailed.</p><div id="cpq-order-panel"></div>';
  renderSubmittedOrder(details);
  cpqEl('#cpq-result').scrollIntoView({block:'start'});
}
async function refreshEmailConfig(){
  const response=await fetch('/api/email/config');
  if(!response.ok)throw new Error('Could not load email settings');
  cpqEmailConfig=await response.json();
}
async function deliverDraftEmail(orderId, form, accessToken){
  const status=cpqEl('#cpq-email-status');
  const button=cpqEl('#cpq-email-form button[type="submit"]');
  status.textContent='Sending draft PDF…';
  try{
    const response=await fetch(`/api/cpq/orders/${encodeURIComponent(orderId)}/email`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({primaryEmail:form.get('primaryEmail'),copyEmail:form.get('copyEmail'),gmailAccessToken:accessToken})});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'Could not send email');
    status.textContent=`Gmail accepted the draft PDF from ${result.sender} for ${result.recipients.join(' and ')}.`;
    button.textContent='Draft email sent';
  }catch(error){status.textContent=error.message;button.disabled=false}
}
async function refreshCpq(){
  const chosenPromotion=cpqEl('#cpq-promotion').value;
  const response=await fetch('/api/cpq/options');
  if(!response.ok)throw new Error('Could not load available products');
  cpqOptions=await response.json();cpqCustomer=cpqOptions.customer;
  cpqEl('#cpq-customer-name').textContent=`${cpqCustomer.givenName} ${cpqCustomer.familyName}`;
  cpqEl('#cpq-customer-meta').textContent=`UK ${cpqCustomer.segment} · example customer`;
  for(const oid of selectedOffers.keys())if(!cpqOptions.offers.some(o=>o.id===oid))selectedOffers.delete(oid);
  renderPromotion(chosenPromotion);renderPlans();renderBasket();
}
cpqEl('#cpq-plan-grid').addEventListener('click',event=>{
  const button=event.target.closest('[data-toggle-offer]');if(!button)return;
  const oid=button.dataset.toggleOffer,offer=cpqOptions.offers.find(o=>o.id===oid);
  if(selectedOffers.has(oid))selectedOffers.delete(oid);else selectedOffers.set(oid,termFor(offer));
  renderPlans();renderBasket();clearQuote();
});
cpqEl('#cpq-plan-grid').addEventListener('change',event=>{
  const input=event.target.closest('[data-term-id]');if(!input)return;
  const oid=input.dataset.termId,months=Number(input.value);
  cardTerms.set(oid,months);if(selectedOffers.has(oid))selectedOffers.set(oid,months);
  renderPlans();renderBasket();clearQuote();
});
cpqEl('#cpq-promotion').addEventListener('change',()=>{showPromotion();renderPlans();renderBasket();clearQuote()});
document.querySelector('[data-view="cpq"]').addEventListener('click',()=>refreshCpq().catch(error=>toast(error.message)));

cpqEl('#cpq-validate').onclick=async()=>{
  const selections=cpqOptions.offers.filter(offer=>selectedOffers.has(offer.id)).map(offer=>({offeringId:offer.id,termMonths:selectedOffers.get(offer.id)}));
  if(!selections.length){cpqEl('#cpq-result').innerHTML='<h2>Choose a product</h2><p role="alert">Select at least one product tile before validating the quote.</p>';return}
  const payload={customerId:cpqCustomer.id,selections,promotionId:cpqEl('#cpq-promotion').value||null};
  try{
    const response=await fetch('/api/cpq/quote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'Could not validate quote');
    const recurring=result.quote.quoteTotalPrice[0].price.dutyFreeAmount.value;
    const setup=result.quote.quoteTotalPrice[1].price.dutyFreeAmount.value;
    cpqEl('#cpq-result').innerHTML=`<div class="result-summary"><h2>Configured quote for ${cpqEsc(cpqCustomer.givenName)} ${cpqEsc(cpqCustomer.familyName)}</h2><span class="result-status ${result.approval.required?'pending':''}">${cpqEsc(result.status)}</span></div><div class="cpq-quote-grid"><div><h3>Selected products</h3>${result.quote.quoteItem.map(item=>`<div class="result-item"><strong>${cpqEsc(item.productOffering.name)} · ${item.termMonths} months</strong><small>${item.product.productCharacteristic.map(c=>`${cpqEsc(c.value)} ${cpqEsc(c.unit)} ${cpqEsc(c.productSpecification?.name||c.name)}`).join(' · ')}</small><small>£${cpqEsc(item.itemPrice[0].price.dutyFreeAmount.value)}/month · ${cpqEsc(item.pricingDecision.discountPercent)}% discount</small></div>`).join('')}</div><div><h3>Price summary</h3><div class="result-line"><span>Monthly before tax</span><strong>£${cpqEsc(recurring)}</strong></div><div class="result-line"><span>Setup before tax</span><strong>£${cpqEsc(setup)}</strong></div><div class="result-line"><span>Estimated selected terms</span><strong>£${cpqEsc(result.commitmentEstimate)}</strong></div><p class="cpq-validation">${result.promotion?`Promotion: ${cpqEsc(result.promotion.name)}. `:''}${result.approval.required?'Human approval required before ordering.':'Configuration valid and ready for review.'}</p><details><summary>Matched rules</summary>${result.ruleDecisions.map(d=>`<div class="result-item">${cpqEsc(d.productOfferingId)} · ${cpqEsc(d.kind)} · ${cpqEsc(d.rowId)}<small>${cpqEsc(d.reason)}</small></div>`).join('')}</details></div></div><p class="form-hint">Quote preview only. No order or network provisioning has occurred.</p>${result.status==='VALIDATED'?`<button type="button" class="primary cpq-submit" data-quote-id="${cpqEsc(result.quote.id)}">Submit POC product order →</button>`:'<p class="cpq-error">Order submission is held until a human approves this quote.</p>'}<div id="cpq-order-panel"></div>`;
  }catch(error){cpqEl('#cpq-result').innerHTML=`<h2>Configuration needs attention</h2><p role="alert" class="cpq-error">${cpqEsc(error.message)}</p>`}
  cpqEl('#cpq-result').scrollIntoView({behavior:'smooth',block:'start'});
};
cpqEl('#cpq-result').addEventListener('click',async event=>{
  const button=event.target.closest('[data-quote-id]');if(!button)return;
  button.disabled=true;button.textContent='Submitting order…';
  try{
    const prepared=await fetch(`/api/cpq/quotes/${encodeURIComponent(button.dataset.quoteId)}/order-payload`);
    const draft=await prepared.json();if(!prepared.ok)throw new Error(draft.error||'Could not prepare order');
    const submitted=await fetch('/tmf-api/productOrderingManagement/v5/productOrder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft.productOrder)});
    const order=await submitted.json();if(!submitted.ok)throw new Error(order.error||'Could not submit order');
    const response=await fetch(`/api/cpq/orders/${encodeURIComponent(order.id)}`);
    const details=await response.json();if(!response.ok)throw new Error(details.error||'Could not load order');
    renderSubmittedOrder(details);button.textContent='Order submitted';
    window.history.replaceState(null,'',`?order=${encodeURIComponent(order.id)}`);
  }catch(error){button.disabled=false;button.textContent='Submit POC product order →';cpqEl('#cpq-order-panel').innerHTML=`<p role="alert" class="cpq-error">${cpqEsc(error.message)}</p>`}
});
cpqEl('#cpq-result').addEventListener('submit',async event=>{
  if(event.target.id!=='cpq-email-form')return;
  event.preventDefault();
  const orderId=cpqEl('#cpq-order-panel').dataset.orderId;
  const form=new FormData(event.target);
  const status=cpqEl('#cpq-email-status');
  const button=event.target.querySelector('button[type="submit"]');
  if(String(form.get('primaryEmail')).toLowerCase().endsWith('@example.com')){
    status.textContent='Replace the fictional example.com address before sending.';return;
  }
  if(!cpqEmailConfig){status.textContent='Loading Google email settings. Please try again in a moment.';refreshEmailConfig().catch(()=>{});return}
  if(!cpqEmailConfig.configured){status.textContent='Google email setup is still required for this project.';return}
  if(cpqEmailConfig.provider!=='gmail'){
    button.disabled=true;
    await deliverDraftEmail(orderId,form,null);
    return;
  }
  if(!window.google?.accounts?.oauth2){status.textContent='Google sign-in is still loading. Please try again in a moment.';return}
  button.disabled=true;
  status.textContent='Choose the Google mailbox that will send this draft PDF…';
  try{
    const tokenClient=google.accounts.oauth2.initTokenClient({
      client_id:cpqEmailConfig.clientId,
      scope:'openid email https://www.googleapis.com/auth/gmail.send',
      callback:response=>{
        if(response.error||!response.access_token){status.textContent='Google did not authorize Gmail sending.';button.disabled=false;return}
        if(!google.accounts.oauth2.hasGrantedAllScopes(response,'https://www.googleapis.com/auth/gmail.send')){
          status.textContent='Gmail send permission was not selected. Try again and tick “Send email on your behalf” in Google’s consent window.';
          button.disabled=false;
          return;
        }
        deliverDraftEmail(orderId,form,response.access_token);
      },
      error_callback:()=>{status.textContent='Google sign-in was closed or blocked. Please try again.';button.disabled=false}
    });
    tokenClient.requestAccessToken();
  }catch(error){status.textContent=`Google sign-in could not start: ${error.message}`;button.disabled=false}
});
Promise.all([refreshCpq(),refreshEmailConfig()]).then(openExistingOrderFromUrl).catch(error=>toast(error.message));
