(async function(){
  const categories = [
    'Booking a Service','Cancel a Service','Payment & Refund','Service Provider Issues','Customer Issues','Account & Profile','Safety & Emergency','Report a Problem','Technical Issues','Other'
  ];

  function el(html){ const d=document.createElement('div'); d.innerHTML=html.trim(); return d.firstChild; }

  function renderCategories(){
    const container = document.getElementById('categories');
    container.innerHTML='';
    categories.forEach(c=>{
      const card = el(`<button class="co-op-card" data-cat="${c}" style="text-align:left;padding:14px;">\n        <div style=\"display:flex;align-items:center;gap:10px;\">\n          <div class=\"co-op-icon\">❓</div>\n          <div>\n            <div style=\"font-weight:700;\">${c}</div>\n            <div style=\"font-size:0.85rem;color:var(--neutral-600);margin-top:6px;\">Quick help and common fixes</div>\n          </div>\n        </div>\n      </button>`);
      card.onclick = ()=>selectCategory(c);
      container.appendChild(card);
    });
  }

  function showIssuePane(title, issues){
    document.getElementById('issuePane').style.display = 'block';
    document.getElementById('issueTitle').textContent = title;
    const list = document.getElementById('issueList'); list.innerHTML='';
    issues.forEach(i=>{
      const btn = el(`<button class="btn" style="text-align:left;padding:12px;">${i}</button>`);
      btn.onclick = ()=>showSolution(title, i);
      list.appendChild(btn);
    });
  }

  function showSolution(category, issue){
    document.getElementById('solutionPane').style.display = 'block';
    document.getElementById('solutionTitle').textContent = issue;
    // Lightweight canned solutions, could be replaced by help/article lookup
    const sample = `<p><strong>Problem:</strong> ${issue}</p><p>Try these steps:</p><ol><li>Check your booking details and status in the Jobs page.</li><li>Contact the provider via Messages.</li><li>If unresolved, submit a complaint below and include evidence.</li></ol>`;
    document.getElementById('solutionBody').innerHTML = sample;
    document.getElementById('helpYes').onclick = ()=>{ alert('Glad we could help!'); };
    document.getElementById('helpNo').onclick = ()=>{ showComplaintForm(issue); };
  }

  function showComplaintForm(issue){
    document.getElementById('complaintForm').style.display = 'block';
    document.getElementById('complaintForm').scrollIntoView({behavior:'smooth'});
    const f = document.getElementById('complaintFormEl');
    f.subject.value = issue;
  }
  window.hideComplaintForm = ()=>{ document.getElementById('complaintForm').style.display='none'; }

  async function submitComplaint(ev){
    ev.preventDefault();
    const form = ev.target;
    const data = new FormData(form);
    // attach current user booking context if present
    try{
      const res = await fetch('/api/complaints', { method:'POST', body: data, credentials:'same-origin'});
      const json = await res.json();
      if (!res.ok) throw new Error(json.error||'Error');
      // show complaint registered
      document.getElementById('complaintForm').style.display='none';
      const body = document.getElementById('complaintStatusBody');
      body.innerHTML = `<p>Your complaint ID: <strong>${json.complaint_id}</strong></p><p>Reference: <strong>${json.complaint_uuid || ''}</strong></p><p>Status: Submitted</p><div style="margin-top:12px;"><button class='btn btn-primary' onclick="location.href='/help.html'">Back to Help</button></div>`;
      document.getElementById('complaintStatus').style.display='block';
    }catch(err){ toast('Failed to submit complaint: '+err.message, 'error'); }
  }

  async function suggest(query){
    const s = document.getElementById('suggestions'); s.innerHTML='';
    if (!query) return;
    try{
      const res = await fetch('/api/help/search?q='+encodeURIComponent(query));
      const items = await res.json();
      items.slice(0,5).forEach(it=>{
        const b = el(`<button class="btn" style="padding:8px 12px;">${it.title}</button>`);
        b.onclick = ()=>{ showArticle(it.id); };
        s.appendChild(b);
      });
    }catch(e){}
  }

  async function showArticle(id){
    try{
      const res = await fetch('/api/help/articles');
      const list = await res.json();
      const found = list.find(x=>x.id==id);
      if(found){
        document.getElementById('solutionPane').style.display='block';
        document.getElementById('solutionTitle').textContent = found.title;
        document.getElementById('solutionBody').textContent = found.category || '';
      }
    }catch(e){}
  }

  function selectCategory(cat){
    // sample mapping
    const map = {
      'Booking a Service':['My service hasn\'t been accepted','Provider hasn\'t arrived','I want to reschedule','I want to cancel my booking','Wrong service/provider assigned','Service was not completed'],
      'Payment & Refund':['Payment failed','Money deducted but booking failed','Refund not received','Incorrect amount charged','Payment made twice'],
      'Service Provider Issues':['Provider is late','Provider didn\'t complete the work','Provider behaved improperly','Quality of service was poor','I want to report a provider'],
      'Safety & Emergency':['Report unsafe behavior','Report harassment','Report suspicious activity','Emergency assistance']
    };
    const issues = map[cat] || ['General question related to '+cat];
    showIssuePane(cat, issues);
  }

  document.getElementById('helpSearch').addEventListener('input', e=>{
    suggest(e.target.value);
  });

  document.getElementById('complaintFormEl').addEventListener('submit', submitComplaint);

  renderCategories();
})();
