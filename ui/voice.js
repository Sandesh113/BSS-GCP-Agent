// Short voice capture for a text field: record up to 30 s, transcribe with Gemini, then the person edits the text.
window.attachVoiceInput=function({button,note,target,onRecording=()=>{}}){
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
    button.classList.add('hidden');
    note.textContent='Voice recording is unavailable in this browser. You can type instead.';
    return;
  }
  let recorder=null,timer=null;
  const reset=()=>{button.textContent='🎙';button.classList.remove('recording');button.disabled=false;onRecording(false)};
  button.addEventListener('click',async()=>{
    if(recorder){if(recorder.state==='recording')recorder.stop();return}
    const mimeType=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/ogg','audio/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
    if(!mimeType){note.textContent='This browser cannot record a supported audio format. Please type instead.';return}
    button.disabled=true;note.textContent='Requesting microphone access…';
    let stream;
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:true});
      const chunks=[];
      recorder=new MediaRecorder(stream,{mimeType,audioBitsPerSecond:64000});
      recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data)};
      recorder.onstop=async()=>{
        clearTimeout(timer);stream.getTracks().forEach(track=>track.stop());
        const blob=new Blob(chunks,{type:recorder.mimeType});recorder=null;reset();
        if(!blob.size||blob.size>2*1024*1024){note.textContent='The recording was empty or too long. Please try again, or type instead.';return}
        note.textContent='Transcribing with Gemini…';button.disabled=true;
        try{
          const form=new FormData();form.append('audio',blob,'answer.'+(mimeType.includes('mp4')?'m4a':mimeType.includes('ogg')?'ogg':'webm'));
          const response=await fetch('/api/catalogue/assistant/transcribe',{method:'POST',body:form});
          const data=await response.json();
          if(!response.ok)throw new Error(data.error||'Transcription failed');
          target.value=[target.value.trim(),data.transcript].filter(Boolean).join(' ');
          note.textContent='Check the transcribed text, then continue.';target.focus();
        }catch(error){note.textContent=error.message+' You can type instead.'}
        finally{button.disabled=false}
      };
      recorder.start();
      button.textContent='■';button.classList.add('recording');button.disabled=false;onRecording(true);
      note.textContent='Recording… press Stop when finished (maximum 30 seconds).';
      timer=setTimeout(()=>{if(recorder?.state==='recording')recorder.stop()},30000);
    }catch(error){
      if(stream)stream.getTracks().forEach(track=>track.stop());
      recorder=null;reset();
      note.textContent=error.name==='NotAllowedError'?'Microphone access was blocked. Allow this site to use your microphone, or type instead.'
        :error.name==='NotFoundError'?'No microphone was found. Connect one, or type instead.'
        :'Voice recording could not start ('+(error.name||'unknown error')+'). Please type instead.';
    }
  });
};
