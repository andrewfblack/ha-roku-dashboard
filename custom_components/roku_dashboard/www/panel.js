/* Family Dashboard panel for the Home Assistant frontend.

The panel is registered by the roku_dashboard integration and shows the same
dashboard as the web app. Signed-in administrators can change the dashboard
configuration straight from the panel.
 */
(function(){
const ASSET='/family-dashboard/';
const BACKGROUNDS=[['fall','Fall'],['winter','Winter'],['spring','Spring'],['summer','Summer'],['uploaded','Uploaded image'],['custom_url','Custom image URL']];
const LAYOUTS=[['home','Home (calendar, meals, climate)'],['compact','Compact (climate first)'],['meals_first','Meals first']];
const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];

function loadHelpers(){
  if(window.FamilyDashboard)return Promise.resolve(window.FamilyDashboard);
  return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=ASSET+'dashboard.js';s.onload=()=>resolve(window.FamilyDashboard);s.onerror=()=>reject(new Error('Unable to load the dashboard assets'));document.head.appendChild(s)});
}

class FamilyDashboardPanel extends HTMLElement{
  constructor(){
    super();
    this.attachShadow({mode:'open'});
    this._hass=null;
    this._data=null;
    this._tab='home';
    this._timer=null;
    this._clock=null;
    this._backgroundUrl='';
    this._idleTimer=null;
  }

  set hass(hass){this._hass=hass;if(this.isConnected)this._updateAccess()}
  set narrow(narrow){this._narrow=narrow}
  set route(route){this._route=route}
  getCardSize(){return 12}

  connectedCallback(){
    this._build();
    this._updateAccess();
    loadHelpers().then(()=>this._refresh()).catch(error=>console.error(error));
    this._timer=setInterval(()=>this._refresh(),15000);
    this._clock=setInterval(()=>this._updateClock(),1000);
    this._resetIdle();
  }

  disconnectedCallback(){clearInterval(this._timer);clearInterval(this._clock);clearTimeout(this._idleTimer);this._timer=null;this._clock=null;this._idleTimer=null}

  _updateAccess(){
    const edit=this.shadowRoot.querySelector('#edit');
    const admin=!!(this._hass&&this._hass.user&&this._hass.user.is_admin);
    if(edit)edit.hidden=!admin;
    const pairing=this.shadowRoot.querySelector('#pairing');
    if(pairing)pairing.hidden=!admin;
  }

  /* ------------------------------------------------------------------ */
  /* Rendering                                                           */
  /* ------------------------------------------------------------------ */

  _build(){
    const root=this.shadowRoot;
    root.innerHTML=`
      <link rel="stylesheet" href="${ASSET}app.css">
      <link rel="stylesheet" href="${ASSET}panel.css">
      <div id="background"></div>
      <div id="app">
        <header>
          <div><h1 id="dashboardTitle">Family Dashboard</h1><div id="clock"></div></div>
          <nav id="tabs" aria-label="Dashboard tabs"></nav>
          <div class="header-actions"><button id="pairing" class="icon-button" title="Pair a device" aria-label="Pair a device"><img src="${ASSET}mdi/link-variant.svg" alt=""></button><button id="edit" class="icon-button" title="Change the dashboard settings" aria-label="Change dashboard settings"><img src="${ASSET}mdi/settings.svg" alt=""></button></div>
        </header>
        <div id="notice" role="status" hidden></div>
        <main id="content"><div class="loading">Loading…</div></main>
      </div>
      <dialog id="mealDialog">
        <h2>Weekly Meal Plan</h2>
        <div id="weeklyMeals" class="week-meals"></div>
        <button id="saveMeals" class="primary">Save week</button>
        <button id="closeMeals">Cancel</button>
      </dialog>
      <dialog id="todayDialog">
        <h2>Today’s Events</h2>
        <div id="todayEvents" class="dialog-events"></div>
        <button id="closeToday" class="primary">Close</button>
      </dialog>
      <dialog id="pairingDialog">
        <h2>Paired devices</h2>
        <div id="pairingBody"></div>
        <div class="fd-actions"><button type="button" id="closePairing" class="primary">Close</button></div>
      </dialog>
      <dialog id="settingsDialog">
        <form id="settingsForm">
          <h2>Family Dashboard settings</h2>
          <div id="settingsBody"></div>
          <div class="fd-actions"><button type="submit" class="primary">Save settings</button><button type="button" id="closeSettings">Cancel</button></div>
        </form>
      </dialog>`;
    root.querySelector('#edit').onclick=()=>this._openSettings();
    root.querySelector('#pairing').onclick=()=>this._openPairing();
    root.querySelector('#closePairing').onclick=()=>root.querySelector('#pairingDialog').close();
    root.querySelector('#closeSettings').onclick=()=>root.querySelector('#settingsDialog').close();
    root.querySelector('#closeMeals').onclick=()=>root.querySelector('#mealDialog').close();
    root.querySelector('#saveMeals').onclick=()=>this._saveMeals();
    root.querySelector('#closeToday').onclick=()=>root.querySelector('#todayDialog').close();
    root.addEventListener('pointerdown',()=>this._resetIdle(),{passive:true});
    root.addEventListener('keydown',()=>this._resetIdle(),{passive:true});
    root.querySelector('#settingsForm').onsubmit=e=>{e.preventDefault();this._saveSettings()};
    this._updateClock();
  }

  _resetIdle(){
    clearTimeout(this._idleTimer);
    this._idleTimer=setTimeout(()=>{this._tab='home';this._renderNav();this._render();this.scrollTo({top:0,behavior:'smooth'})},300000);
  }

  _updateClock(){
    const clock=this.shadowRoot.querySelector('#clock');
    if(!clock)return;
    const d=new Date();
    clock.textContent=d.toLocaleDateString([],{weekday:'long',month:'long',day:'numeric'})+' · '+d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
  }

  async _refresh(){
    if(!this._hass||!this.isConnected)return;
    try{
      const data=await this._hass.callApi('GET','family_dashboard/panel');
      this._data=data;
      const notice=this.shadowRoot.querySelector('#notice');
      if(notice&&!notice.classList.contains('info'))this._showNotice('');
      this._applyBackground();
      this._renderNav();
      this._render();
    }catch(error){
      this._showNotice(`Unable to load the dashboard: ${error.message||error}`);
      const content=this.shadowRoot.querySelector('#content');
      if(content&&!this._data)content.innerHTML='<div class="loading">Waiting for connection…</div>';
    }
  }

  _showNotice(message,kind='error'){
    const notice=this.shadowRoot.querySelector('#notice');
    if(!notice)return;
    notice.textContent=message;
    notice.className=kind==='info'?'info':'';
    notice.hidden=!message;
  }

  async _applyBackground(){
    const background=this.shadowRoot.querySelector('#background');
    const data=this._data;
    if(!background||!data||!window.FamilyDashboard)return;
    window.FamilyDashboard.applyTheme(this,data);
    if(data.background==='uploaded'&&data.has_uploaded_background){
      const url=await this._uploadedBackground();
      background.style.backgroundImage=url?`url("${url}")`:'';
      return;
    }
    background.style.backgroundImage=window.FamilyDashboard.backgroundImage(data);
  }

  async _uploadedBackground(){
    try{
      const token=this._hass&&this._hass.auth?this._hass.auth.data.access_token:'';
      const response=await fetch('/api/family_dashboard/panel/background',{headers:token?{Authorization:`Bearer ${token}`}:{}});
      if(!response.ok)return '';
      const blob=await response.blob();
      if(this._backgroundUrl)URL.revokeObjectURL(this._backgroundUrl);
      this._backgroundUrl=URL.createObjectURL(blob);
      return this._backgroundUrl;
    }catch(error){return ''}
  }

  _renderNav(){
    const nav=this.shadowRoot.querySelector('#tabs');
    if(!nav||!this._data)return;
    const tabs=window.FamilyDashboard.enabledTabs(this._data);
    if(!tabs.some(([id])=>id===this._tab))this._tab='home';
    nav.innerHTML=tabs.map(([id,label,icon])=>`<button data-tab="${id}" class="tab-button ${id===this._tab?'active':''}" title="${window.FamilyDashboard.esc(label)}" aria-label="${window.FamilyDashboard.esc(label)}"><img src="${window.FamilyDashboard.mdi(icon)}" alt=""></button>`).join('');
    nav.querySelectorAll('button').forEach(b=>b.onclick=()=>{this._tab=b.dataset.tab;this._renderNav();this._render()});
  }

  _render(){
    const data=this._data;
    const content=this.shadowRoot.querySelector('#content');
    if(!data||!content||!window.FamilyDashboard)return;
    const FD=window.FamilyDashboard;
    this.shadowRoot.querySelector('#dashboardTitle').textContent=data.title||'Family Dashboard';
    const views={home:FD.renderHome,calendar:FD.renderCalendar,weather:FD.renderWeather,lights:FD.renderLights,scenes:FD.renderScenes,climate:FD.renderClimate};
    content.innerHTML=(views[this._tab]||FD.renderHome)(data);
    this._bindActions();
  }

  _bindActions(){
    const root=this.shadowRoot;
    const run=body=>this._action(body).catch(error=>this._showNotice(`Control error: ${error.message||error}`));
    root.querySelectorAll('.toggle').forEach(b=>b.onclick=()=>run({action:'light_toggle',entity_id:b.dataset.id}));
    root.querySelectorAll('[data-bright]').forEach(b=>b.onclick=()=>run({action:'light_brightness',entity_id:b.dataset.id,value:Number(b.dataset.bright)}));
    root.querySelectorAll('.scene').forEach(b=>b.onclick=()=>run({action:'scene_activate',entity_id:b.dataset.id}));
    root.querySelectorAll('[data-temp]').forEach(b=>b.onclick=()=>run({action:'climate_temperature',entity_id:b.dataset.id,value:Number(b.dataset.temp)}));
    root.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>run({action:'climate_mode',entity_id:b.dataset.id,value:b.dataset.mode}));
    const meal=root.querySelector('#mealPanel');
    if(meal)meal.onclick=()=>this._openMeals();
    const today=root.querySelector('#todayPanel');
    if(today)today.onclick=()=>this._openToday();
  }

  async _action(body){
    await this._hass.callApi('POST','family_dashboard/panel/action',body);
    await this._refresh();
  }

  /* ------------------------------------------------------------------ */
  /* Weekly meals                                                        */
  /* ------------------------------------------------------------------ */

  _openMeals(){
    const rows=(this._data&&this._data.weekly_meal_plan)||[];
    const box=this.shadowRoot.querySelector('#weeklyMeals');
    box.innerHTML=rows.map((r,i)=>`<label class="week-meal ${r.is_today?'today':''}"><b>${window.FamilyDashboard.esc(r.day)}</b><input data-meal-day="${i}" maxlength="120" value="${window.FamilyDashboard.esc(r.meal||'')}"></label>`).join('');
    this.shadowRoot.querySelector('#mealDialog').showModal();
  }

  async _saveMeals(){
    const values=[...this.shadowRoot.querySelectorAll('[data-meal-day]')].map(i=>i.value);
    try{
      await this._action({action:'meal_week',value:values});
      this.shadowRoot.querySelector('#mealDialog').close();
    }catch(error){this._showNotice(`Control error: ${error.message||error}`)}
  }

  _openToday(){
    const events=(this._data&&this._data.today_events)||((this._data&&this._data.calendar_events)||[]);
    const box=this.shadowRoot.querySelector('#todayEvents');
    box.innerHTML=events.length?events.map(window.FamilyDashboard.eventHTML).join(''):'<div class="empty compact">No events today</div>';
    this.shadowRoot.querySelector('#todayDialog').showModal();
  }

  /* ------------------------------------------------------------------ */
  /* Pairing                                                             */
  /* ------------------------------------------------------------------ */

  async _openPairing(){
    const root=this.shadowRoot;
    const body=root.querySelector('#pairingBody');
    const esc=window.FamilyDashboard.esc;
    let state;
    try{
      state=await this._hass.callApi('GET','family_dashboard/panel/pairing');
    }catch(error){
      body.innerHTML='<div class="empty compact">Unable to load the paired devices.</div>';
      root.querySelector('#pairingDialog').showModal();
      return;
    }
    const pending=(state.pending||[]).map(r=>`<div class="fd-pair-row"><div><b>${esc(r.name||'Unknown device')}</b><small>${esc(r.platform)}${r.remote?' · '+esc(r.remote):''}${r.app_version?' · '+esc(r.app_version):''}</small><code>${esc(r.device_code)}</code></div><div><button class="primary" data-approve="${esc(r.device_code)}">Approve</button><button data-deny="${esc(r.device_code)}">Deny</button></div></div>`).join('');
    const devices=(state.devices||[]).map(d=>`<div class="fd-pair-row"><div><b>${esc(d.name||'Unknown device')}</b><small>${esc(d.platform)}${d.last_seen?' · last seen '+esc(d.last_seen):''}</small></div><div><button data-revoke="${esc(d.device_id)}">Revoke</button></div></div>`).join('');
    const legacy=state.legacy_token?`<div class="fd-pair-row"><div><b>Legacy shared token</b><small>Used by clients that paired before per-device credentials</small></div><div><button data-revoke-legacy="1">Revoke</button></div></div>`:'';
    body.innerHTML=`<h3>Waiting for approval</h3>${pending||'<div class="empty compact">No device is waiting to pair.</div>'}<h3>Paired devices</h3>${devices||'<div class="empty compact">No device is paired yet.</div>'}${legacy}`;
    body.querySelectorAll('[data-approve]').forEach(b=>b.onclick=()=>this._pairingAction({action:'approve',device_code:b.dataset.approve}));
    body.querySelectorAll('[data-deny]').forEach(b=>b.onclick=()=>this._pairingAction({action:'deny',device_code:b.dataset.deny}));
    body.querySelectorAll('[data-revoke]').forEach(b=>b.onclick=()=>this._pairingAction({action:'revoke',device_id:b.dataset.revoke}));
    const revokeLegacy=body.querySelector('[data-revoke-legacy]');
    if(revokeLegacy)revokeLegacy.onclick=()=>this._pairingAction({action:'revoke_legacy'});
    root.querySelector('#pairingDialog').showModal();
  }

  async _pairingAction(body){
    try{
      await this._hass.callApi('POST','family_dashboard/panel/pairing',body);
      this._showNotice('Done.','info');
    }catch(error){
      this._showNotice(`Unable to update the paired devices: ${error.message||error}`);
    }
    await this._openPairing();
  }

  /* ------------------------------------------------------------------ */
  /* Settings                                                            */
  /* ------------------------------------------------------------------ */

  _entities(domain){
    const states=this._hass.states;
    return Object.keys(states).filter(id=>id.startsWith(`${domain}.`)).sort().map(id=>({id,label:states[id].attributes.friendly_name||id}));
  }

  _options(items,value,multiple){
    const selected=multiple?(Array.isArray(value)?value:[]):[value];
    return items.map(item=>`<option value="${window.FamilyDashboard.esc(item.id)}"${selected.includes(item.id)?' selected':''}>${window.FamilyDashboard.esc(item.label)}</option>`).join('');
  }

  _select(name,label,items,value,multiple){
    const selected=multiple?(Array.isArray(value)?value:[]):[value];
    const list=items.slice();
    selected.forEach(id=>{if(id&&!list.some(item=>item.id===id))list.push({id,label:id})});
    const choices=multiple?list:[{id:'',label:'— none —'}].concat(list);
    return `<label class="fd-field"><span>${label}</span><select name="${name}"${multiple?' multiple size="5"':''}>${this._options(choices,value,multiple)}</select></label>`;
  }

  _toggle(name,label,checked){
    return `<label class="fd-toggle"><input type="checkbox" name="${name}"${checked?' checked':''}><span>${label}</span></label>`;
  }

  _color(name,label,value){
    return `<label class="fd-field fd-color"><span>${label}</span><input type="color" name="${name}" value="${value||'#000000'}"></label>`;
  }

  async _openSettings(){
    const root=this.shadowRoot;
    let options;
    try{
      const response=await this._hass.callApi('GET','family_dashboard/panel/settings');
      options=response.options;
    }catch(error){
      this._showNotice(`Unable to open the settings: ${error.message||error}`);
      return;
    }
    const esc=window.FamilyDashboard.esc;
    const body=root.querySelector('#settingsBody');
    const backgrounds=BACKGROUNDS.filter(([id])=>id!=='uploaded'||options.has_uploaded_background);
    body.innerHTML=`
      <div class="fd-grid">
        <label class="fd-field"><span>Dashboard name</span><input type="text" name="dashboard_title" maxlength="60" value="${esc(options.dashboard_title||'')}"></label>
        <label class="fd-field"><span>Background</span><select name="background">${this._options(backgrounds.map(([id,label])=>({id,label})),options.background,false)}</select></label>
        <label class="fd-field"><span>Custom background URL</span><input type="text" name="background_url" value="${esc(options.background_url||'')}"></label>
        <label class="fd-field"><span>Layout</span><select name="layout">${this._options(LAYOUTS.map(([id,label])=>({id,label})),options.layout,false)}</select></label>
        ${this._select('indoor_entity','Indoor temperature',this._entities('sensor').concat(this._entities('climate')),options.indoor_entity,false)}
        ${this._select('indoor_humidity_entity','Indoor humidity',this._entities('sensor'),options.indoor_humidity_entity,false)}
        ${this._select('outdoor_entity','Outdoor weather',this._entities('weather'),options.outdoor_entity,false)}
        ${this._select('meal_entity','Meal plan helper',this._entities('input_text').concat(this._entities('text')),options.meal_entity,false)}
        ${this._select('calendar_entities','Calendars',this._entities('calendar'),options.calendar_entities,true)}
        ${this._select('light_entities','Lights',this._entities('light'),options.light_entities,true)}
        ${this._select('scene_entities','Scenes and scripts',this._entities('scene').concat(this._entities('script')),options.scene_entities,true)}
        ${this._select('climate_entities','Climate entities',this._entities('climate'),options.climate_entities,true)}
      </div>
      <h3>Tabs</h3>
      <div class="fd-toggles">
        ${this._toggle('weather_tab_enabled','Weather',options.weather_tab_enabled!==false)}
        ${this._toggle('calendar_tab_enabled','Calendar',options.calendar_tab_enabled!==false)}
        ${this._toggle('lights_tab_enabled','Lights',options.lights_tab_enabled!==false)}
        ${this._toggle('scenes_tab_enabled','Scenes',options.scenes_tab_enabled!==false)}
        ${this._toggle('climate_tab_enabled','Climate',options.climate_tab_enabled!==false)}
      </div>
      <h3>Theme and colors</h3>
      <div class="fd-grid fd-theme-grid">
        ${this._color('theme_header_text','Header text',options.theme_header_text)}
        ${this._color('theme_item_header_text','Card heading text',options.theme_item_header_text)}
        ${this._color('theme_body_text','Body text',options.theme_body_text)}
        ${this._color('theme_muted_text','Secondary text',options.theme_muted_text)}
        ${this._color('theme_accent','Accent',options.theme_accent)}
        ${this._color('theme_background','Fallback background',options.theme_background)}
        ${this._color('theme_item_background','Card background',options.theme_item_background)}
        ${this._color('theme_selected_background','Selected background',options.theme_selected_background)}
        ${this._color('theme_selected_border','Selected border',options.theme_selected_border)}
        ${this._color('theme_item_border','Card border',options.theme_item_border)}
        <label class="fd-field"><span>Card opacity: <output id="itemOpacityOutput">${options.theme_item_opacity}</output>%</span><input type="range" name="theme_item_opacity" min="0" max="100" value="${options.theme_item_opacity}"></label>
        <label class="fd-field"><span>Background darkening: <output id="overlayOutput">${options.theme_background_overlay}</output>%</span><input type="range" name="theme_background_overlay" min="0" max="100" value="${options.theme_background_overlay}"></label>
      </div>
      <h3>Weekly meal plan</h3>
      <div class="fd-grid">
        ${DAYS.map((day,index)=>`<label class="fd-field"><span>${day}</span><input type="text" maxlength="120" name="meal_${index}" value="${esc(options[`meal_${day.toLowerCase()}`]||'')}"></label>`).join('')}
      </div>`;
    root.querySelector('#settingsDialog').showModal();
    const itemOpacity=root.querySelector('[name="theme_item_opacity"]');
    const overlay=root.querySelector('[name="theme_background_overlay"]');
    itemOpacity.oninput=()=>root.querySelector('#itemOpacityOutput').value=itemOpacity.value;
    overlay.oninput=()=>root.querySelector('#overlayOutput').value=overlay.value;
  }

  async _saveSettings(){
    const root=this.shadowRoot;
    const form=root.querySelector('#settingsForm');
    const value=name=>{const field=form.querySelector(`[name="${name}"]`);return field?field.value:''};
    const checked=name=>{const field=form.querySelector(`[name="${name}"]`);return field?field.checked:false};
    const list=name=>[...form.querySelectorAll(`[name="${name}"] option:checked`)].map(o=>o.value).filter(Boolean);
    const options={
      dashboard_title:value('dashboard_title'),
      background:value('background'),
      background_url:value('background_url'),
      layout:value('layout'),
      indoor_entity:value('indoor_entity'),
      indoor_humidity_entity:value('indoor_humidity_entity'),
      outdoor_entity:value('outdoor_entity'),
      meal_entity:value('meal_entity'),
      calendar_entities:list('calendar_entities'),
      light_entities:list('light_entities'),
      scene_entities:list('scene_entities'),
      climate_entities:list('climate_entities'),
      weather_tab_enabled:checked('weather_tab_enabled'),
      calendar_tab_enabled:checked('calendar_tab_enabled'),
      lights_tab_enabled:checked('lights_tab_enabled'),
      scenes_tab_enabled:checked('scenes_tab_enabled'),
      climate_tab_enabled:checked('climate_tab_enabled'),
      theme_header_text:value('theme_header_text'),
      theme_item_header_text:value('theme_item_header_text'),
      theme_body_text:value('theme_body_text'),
      theme_muted_text:value('theme_muted_text'),
      theme_accent:value('theme_accent'),
      theme_background:value('theme_background'),
      theme_item_background:value('theme_item_background'),
      theme_selected_background:value('theme_selected_background'),
      theme_selected_border:value('theme_selected_border'),
      theme_item_border:value('theme_item_border'),
      theme_item_opacity:Number(value('theme_item_opacity')),
      theme_background_overlay:Number(value('theme_background_overlay')),
    };
    DAYS.forEach((day,index)=>{options[`meal_${day.toLowerCase()}`]=value(`meal_${index}`)});
    try{
      await this._hass.callApi('POST','family_dashboard/panel/settings',{options});
      root.querySelector('#settingsDialog').close();
      this._showNotice('The dashboard settings were saved.','info');
      await this._refresh();
    }catch(error){
      this._showNotice(`Unable to save the settings: ${error.message||error}`);
    }
  }
}

customElements.define('roku-dashboard-panel',FamilyDashboardPanel);
})();
