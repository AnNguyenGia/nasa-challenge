const {spawnSync}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const root=path.resolve(__dirname,'..'),backend=path.join(root,'astrohealth-backend');
const python=process.env.ASTRO_PYTHON||path.join(backend,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const checks=[['JavaScript syntax',process.execPath,['--check',path.join(root,'dist/app.js')]],['Components syntax',process.execPath,['--check',path.join(root,'dist/components.js')]],['Electron syntax',process.execPath,['--check',path.join(root,'main.js')]],['Backend safety/integration',python,['-m','pytest','-q','-p','no:cacheprovider']],['Ruff',python,['-m','ruff','check','app','scripts','migrations','tests']],['Strict typing',python,['-m','mypy','--cache-dir=nul','--strict','app']]];
if(!fs.existsSync(python)){console.error('Python environment missing. Run start-local.ps1 first.');process.exit(1);}
for(const [name,exe,args] of checks){console.log(name);const result=spawnSync(exe,args,{cwd:backend,stdio:'inherit',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});if(result.error)console.error(result.error.message);if(result.status!==0)process.exit(result.status||1);}
console.log('All checks passed.');
