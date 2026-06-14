const fs = require('fs');
let content = fs.readFileSync('web/static/app.js', 'utf8');

// Mock DOM
global.document = {
  getElementById: (id) => ({
    textContent: '',
    innerHTML: '',
    style: {},
    classList: { add: ()=>{}, remove: ()=>{} }
  }),
  querySelectorAll: () => []
};
global.showScreen = (x) => console.log('showScreen called with', x);
global.addLog = (x) => console.log('addLog', x);
global.toast = (x) => console.log('toast', x);
global.state = {};

content = content.replace(/document\.addEventListener/g, '/*removed*/');
// Evaluate in global context
const vm = require('vm');
vm.runInThisContext(content);

const data = JSON.parse(fs.readFileSync('data/replays/038947AB.json', 'utf8'));
const pkt = { type: 'REPLAY', room_id: data.room_id, events: data.events };

onReplay(pkt);
