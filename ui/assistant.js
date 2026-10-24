let assistantState = null;
let assistantBusy = false;
let assistantRecorder = null;
let assistantVoiceTimer = null;
let assistantVoiceGeneration = 0;
const assistantEl = selector => document.querySelector(selector);
const assistantEsc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

function assistantBubble(role, message){
  const bubble=document.createElement('div');
  bubble.className=`assistant-bubble ${role}`;
  bubble.textContent=message;
  assistantEl('#assistant-thread').append(bubble);
  bubble.scrollIntoView({block:'end'});
}
function assistantError(message){assistantEl('#assistant-error').textContent=message||''}
function assistantSetBusy(value){
  assistantBusy=value;
  assistantEl('#assistant-send').disabled=value;
  assistantEl('#assistant-create').disabled=value;
  assistantEl('#assistant-send').textContent=value?'Reading answer…':'Send answer';
}
function assistantReview(preview){
  const panel=assistantEl('#assistant-review');
  panel.innerHTML=`<h3>${assistantEsc(preview.name)}</h3><p>${preview.allowances.map(item=>`${assistantEsc(item.value)} ${assistantEsc(item.unit)} ${assistantEsc(item.name)}`).join(' · ')}</p><p>£${assistantEsc(preview.monthlyPrice)} per month · £${assistantEsc(preview.setupPrice)} setup · ${assistantEsc((preview.segments||[]).join(' and '))}</p><p>Saving creates a Draft. Publish from the offering card when you are ready for CPQ.</p>`;
  panel.classList.remove('hidden');
  assistantEl('#assistant-create').classList.remove('hidden');
}

assistantEl('#open-assistant').addEventListener('click',async()=>{
  assistantError('');
  if(!await save(true))return;
  const dialog=assistantEl('#assistant-dialog');
  dialog.showModal();
  assistantEl('#assistant-thread').replaceChildren();
  assistantEl('#assistant-review').classList.add('hidden');
  assistantEl('#assistant-create').classList.add('hidden');
  assistantEl('#assistant-answer').value='';
  assistantEl('#assistant-voice-note').textContent=assistantEl('#assistant-mic').classList.contains('hidden')
    ? 'Voice recording is unavailable in this browser. You can type your answer.'
    : 'Type your answer, or press the microphone to record it.';
  assistantBubble('assistant','Tell me what product you want to build. You can describe everything at once or answer one question at a time.');
  try{
    const response=await fetch('/api/catalogue/assistant/start');
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Could not start product assistant');
    assistantState=data.state;
    assistantBubble('assistant',data.step.question);
    assistantEl('#assistant-answer').focus();
  }catch(error){assistantError(error.message)}
});
assistantEl('#close-assistant').addEventListener('click',()=>assistantEl('#assistant-dialog').close());
assistantEl('#assistant-dialog').addEventListener('close',()=>{
  assistantVoiceGeneration++;
  if(assistantVoiceTimer)clearTimeout(assistantVoiceTimer);
  if(assistantRecorder){
    const recorder=assistantRecorder;
    assistantRecorder=null;
    if(recorder.state!=='inactive')recorder.stop();
    recorder.stream.getTracks().forEach(track=>track.stop());
  }
  assistantEl('#assistant-mic').textContent='🎙';
  assistantEl('#assistant-mic').setAttribute('aria-label','Speak your answer');
  assistantEl('#assistant-mic').classList.remove('recording');
  assistantEl('#assistant-mic').disabled=false;
});
assistantEl('#assistant-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const answer=assistantEl('#assistant-answer');
  const message=answer.value.trim();
  if(!message||assistantBusy||!assistantState)return;
  assistantError('');assistantSetBusy(true);
  try{
    const response=await fetch('/api/catalogue/assistant/turn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:assistantState,message})});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Could not read that answer');
    assistantState=data.state;
    assistantBubble('manager',message);
    assistantBubble('assistant',data.step.question);
    answer.value='';
    if(data.ready)assistantReview(data.preview);
    else{assistantEl('#assistant-review').classList.add('hidden');assistantEl('#assistant-create').classList.add('hidden')}
  }catch(error){assistantError(error.message)}
  finally{assistantSetBusy(false);answer.focus()}
});
assistantEl('#assistant-create').addEventListener('click',async()=>{
  if(assistantBusy||!assistantState)return;
  assistantError('');assistantSetBusy(true);
  try{
    const response=await fetch('/api/catalogue/assistant/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:assistantState})});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Could not save the Draft');
    catalogue=data.catalogue;
    render();
    assistantEl('#assistant-dialog').close();
    toast('Draft product saved. Use Publish offer to make it available in CPQ.');
    document.querySelector(`[data-lifecycle="${data.offeringId}"]`)?.scrollIntoView({behavior:'smooth',block:'center'});
  }catch(error){assistantError(error.message)}
  finally{assistantSetBusy(false)}
});

if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
  assistantEl('#assistant-mic').classList.add('hidden');
  assistantEl('#assistant-voice-note').textContent='Voice recording is unavailable in this browser. You can type your answer.';
}else{
  assistantEl('#assistant-mic').addEventListener('click',async()=>{
    const button=assistantEl('#assistant-mic');
    const note=assistantEl('#assistant-voice-note');
    if(assistantRecorder){
      if(assistantRecorder.state==='recording')assistantRecorder.stop();
      return;
    }
    if(assistantBusy||button.disabled)return;
    const mimeType=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/ogg','audio/mp4']
      .find(type=>MediaRecorder.isTypeSupported(type));
    if(!mimeType){note.textContent='This browser cannot record a supported audio format. Please type your answer.';return}
    button.disabled=true;
    note.textContent='Requesting microphone access…';
    const generation=++assistantVoiceGeneration;
    let stream;
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:true});
      if(generation!==assistantVoiceGeneration){stream.getTracks().forEach(track=>track.stop());return}
      const recorder=new MediaRecorder(stream,{mimeType,audioBitsPerSecond:64000});
      const chunks=[];
      assistantRecorder=recorder;
      recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data)};
      recorder.onerror=()=>{note.textContent='Recording failed. Check your microphone, or type your answer.'};
      recorder.onstop=async()=>{
        if(assistantVoiceTimer)clearTimeout(assistantVoiceTimer);
        stream.getTracks().forEach(track=>track.stop());
        assistantRecorder=null;
        button.textContent='🎙';button.setAttribute('aria-label','Speak your answer');button.classList.remove('recording');
        if(generation!==assistantVoiceGeneration){button.disabled=false;assistantEl('#assistant-send').disabled=assistantBusy;return}
        const blob=new Blob(chunks,{type:recorder.mimeType});
        if(!blob.size){note.textContent='No audio was recorded. Please try again or type your answer.';button.disabled=false;assistantEl('#assistant-send').disabled=assistantBusy;return}
        if(blob.size>2*1024*1024){note.textContent='Recording is too large. Please try a shorter answer.';button.disabled=false;assistantEl('#assistant-send').disabled=assistantBusy;return}
        note.textContent='Transcribing with Gemini…';
        try{
          const form=new FormData();form.append('audio',blob,'answer.'+(mimeType.includes('mp4')?'m4a':mimeType.includes('ogg')?'ogg':'webm'));
          const response=await fetch('/api/catalogue/assistant/transcribe',{method:'POST',body:form});
          const data=await response.json();
          if(!response.ok)throw new Error(data.error||'Transcription failed');
          if(generation!==assistantVoiceGeneration)return;
          const answer=assistantEl('#assistant-answer');
          answer.value=[answer.value.trim(),data.transcript].filter(Boolean).join(' ');
          note.textContent='Review the transcribed answer, then press Send answer.';
          answer.focus();
        }catch(error){if(generation===assistantVoiceGeneration)note.textContent=error.message+' You can type your answer.'}
        finally{button.disabled=false;assistantEl('#assistant-send').disabled=assistantBusy}
      };
      recorder.start();
      button.textContent='■';button.setAttribute('aria-label','Stop recording');button.classList.add('recording');button.disabled=false;
      assistantEl('#assistant-send').disabled=true;
      note.textContent='Recording… press Stop when finished (maximum 30 seconds).';
      assistantVoiceTimer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop()},30000);
    }catch(error){
      if(stream)stream.getTracks().forEach(track=>track.stop());
      if(generation!==assistantVoiceGeneration)return;
      button.disabled=false;
      note.textContent=error.name==='NotAllowedError'
        ? 'Microphone access was blocked. Allow this site to use your microphone, or type your answer.'
        : error.name==='NotFoundError'
          ? 'No microphone was found. Connect one, or type your answer.'
          : 'Voice recording could not start ('+(error.name||'unknown error')+'). Please type your answer.';
    }
  });
}
