(async function(){
  // Admin/support dashboard interactions
  async function fetchComplaints(){
    const res = await fetch('/api/complaints', {credentials:'same-origin'});
    const list = await res.json();
    const el = document.getElementById('supportList');
    if(!el) return;
    el.innerHTML='';
    list.forEach(c=>{
      const row = document.createElement('div'); row.className='card';
      row.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;"><div><strong>#${c.id}</strong> ${c.subject||'(no subject)'}<div style="font-size:0.9rem;color:var(--neutral-600)">by ${c.complainant_name}</div></div><div><button class='btn' data-id='${c.id}'>Open</button></div></div>`;
      row.querySelector('button').onclick = ()=>openComplaint(c.id);
      el.appendChild(row);
    });
  }
  window.fetchComplaints = fetchComplaints;

  async function openComplaint(id){
    const res = await fetch('/api/complaints/'+id, {credentials:'same-origin'});
    const data = await res.json();
    const pane = document.getElementById('supportDetail');
    if(!pane) return;
    pane.style.display='block';
    pane.innerHTML = `<div class='card-title'>Complaint #${data.id} - ${data.subject||''}</div><div style='margin-top:8px;'><strong>Status:</strong> ${data.status} <strong style='margin-left:12px;'>Priority:</strong> ${data.priority||'LOW'}</div><div style='margin-top:8px;'>${data.description||''}</div><div style='margin-top:8px;'><strong>Evidence:</strong> ${(data.evidence||[]).map(e=>`<div><a href='${e}' target='_blank'>${e}</a></div>`).join('')}</div><div style='margin-top:12px;'><button class='btn btn-primary' id='markResolved'>Mark Resolved</button><button class='btn' id='addNote'>Add Note</button></div><div id='notes' style='margin-top:12px;'></div>`;
    document.getElementById('markResolved').onclick = async ()=>{
      await fetch('/api/complaints/'+id+'/status', {method:'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'resolved'})});
      fetchComplaints(); openComplaint(id);
    };
    document.getElementById('addNote').onclick = ()=>{
      const note = prompt('Internal note'); if(!note) return; fetch('/api/complaints/'+id+'/note',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({note,note_internal:true})}).then(()=>openComplaint(id));
    };
    const notesEl = pane.querySelector('#notes'); notesEl.innerHTML = '<h4>Notes</h4>'+(data.notes||[]).map(n=>`<div style='padding:8px;border-radius:8px;background:var(--neutral-50);margin-bottom:8px;'><div style='font-size:0.85rem;color:var(--neutral-600)'>${n.created_at} by ${n.author_id}</div><div>${n.note}</div></div>`).join('');
  }

  // auto-initialize if admin page elements present
  document.addEventListener('DOMContentLoaded', ()=>{
    if(document.getElementById('supportList')) fetchComplaints();
  });
})();
