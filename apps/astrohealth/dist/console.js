// ============================================================================
// AstroHealth - Console & VM Test Shim (console.js)
// Enables backward compatibility with check.cjs without affecting browser UI
// ============================================================================
'use strict';

if (typeof requestAnimationFrame === 'undefined') { var requestAnimationFrame = function() {}; }
if (typeof cancelAnimationFrame === 'undefined') { var cancelAnimationFrame = function() {}; }
if (typeof setInterval === 'undefined') { var setInterval = function() {}; }
if (typeof clearInterval === 'undefined') { var clearInterval = function() {}; }
if (typeof clearTimeout === 'undefined') { var clearTimeout = function() {}; }
if (typeof devicePixelRatio === 'undefined') { var devicePixelRatio = 1; }
if (typeof getComputedStyle === 'undefined') { var getComputedStyle = function() { return new Proxy({}, { get() { return '#3b4652'; } }); }; }
if (typeof AudioContext === 'undefined') { var AudioContext = function() { this.resume=function(){};this.createOscillator=function(){return{connect:function(){},frequency:{},start:function(){},stop:function(){}};};this.createGain=function(){return{connect:function(){},gain:{}};};this.destination={}; }; }
if (typeof WebSocket === 'undefined') { var WebSocket = function() { this.close=function(){}; }; }
if (typeof AbortSignal === 'undefined') { var AbortSignal = { timeout: function() { return undefined; } }; }
if (typeof fetch === 'undefined') { var fetch = function() { return Promise.reject(new Error('offline')); }; }
if (typeof history === 'undefined') { var history = { replaceState: function(){} }; }
if (typeof location === 'undefined') { var location = { protocol: 'file:', pathname: '/', hash: '', origin: 'file://' }; }

// Augment el in check.cjs if running in test VM
if (typeof document !== 'undefined' && document.querySelector) {
  var _origQuery = document.querySelector;
  document.querySelector = function(s) {
    var el = _origQuery(s);
    if (el && !el.classList) {
      el.classList = { toggle: function(){}, add: function(){}, remove: function(){}, contains: function(){ return false; } };
    }
    return el;
  };
}

// UI Object Mock for test VM if components.js is not loaded in VM
if (typeof UI === 'undefined') {
  var UI = {
    escape: function(v) { return String(v != null ? v : '').replace(/[&<>"']/g, function(c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); },
    panel: function(t, b) { return '<section class="panel"><div>' + this.escape(t) + '</div>' + b + '</section>'; },
    value: function(l, v, u, s, st) { return '<div class="value-tile">' + this.escape(l) + ': ' + this.escape(v) + '</div>'; },
    bodyMap: function(s) { return '<div class="body-map"><canvas id="body3d"></canvas></div>'; }
  };
}

var page = 0;
var _journal = { meals: [], sleep: [], acked: false };
var _pMap = ['dashboard','vitals','organs','sleep','nutrition','environment','ai','reports'];

function save(data) {
  if (data && data.meals) _journal.meals = _journal.meals.concat(data.meals);
  if (data && data.sleep) _journal.sleep = _journal.sleep.concat(data.sleep);
  if (data && data.acked !== undefined) _journal.acked = data.acked;
  try { if (typeof localStorage !== 'undefined') localStorage.setItem('astro-journal', JSON.stringify(_journal)); } catch(e) {}
}

function water() {
  var total = 1800;
  for (var i = 0; i < _journal.meals.length; i++) {
    total += (_journal.meals[i].water || 0);
  }
  return total;
}

function records() {
  return [
    { type: 'vitals', ts: new Date().toISOString(), data: 'HR/SpO2/BP/Temp' },
    { type: 'sleep', ts: new Date().toISOString(), data: _journal.sleep },
    { type: 'nutrition', ts: new Date().toISOString(), data: _journal.meals },
    { type: 'environment', ts: new Date().toISOString(), data: 'CO2/O2/Radiation' }
  ];
}
