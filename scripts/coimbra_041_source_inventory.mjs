import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const dir = path.resolve("polo-ii-041-evidence");
await mkdir(dir, { recursive: true });
const browser = await chromium.launch({channel:"chrome",headless:true,
 args:["--enable-unsafe-swiftshader","--use-gl=angle","--use-angle=swiftshader","--disable-gpu-sandbox"]});
try {
  const page = await browser.newPage({viewport:{width:1280,height:800},deviceScaleFactor:1});
  const errs = [];
  page.on("pageerror", e=>errs.push(String(e)));
  await page.goto("http://127.0.0.1:4173/037/?streetQA=polo-ii&qaBackend=webgl&poloLook=after",
    {waitUntil:"domcontentloaded",timeout:120000});
  await page.waitForFunction(()=>{
    const a=globalThis.coimbra037;
    return a?.streetQA?.diagnostics().spot === "polo-ii" &&
      a.poloVisual?.metrics().active && !a.poloVisual?.metrics().pending;
  },undefined,{timeout:120000,polling:350});
  const report=await page.evaluate(()=>{
    const root=globalThis.coimbra037.gltf.scene;
    root.updateMatrixWorld(true);
    const names=[];
    const targets=[];
    const words=/vegetation|tree|canop|forest|scrub|undergrowth/i;
    const three=globalThis.coimbra037.renderer.constructor?.name;
    const camera=globalThis.coimbra037.camera.getWorldPosition(globalThis.coimbra037.camera.position.clone());
    function inPatch(x,z){return Math.abs(x+168.37)<=110 && Math.abs(z-748.07)<=110;}
    root.traverse(obj=>{
      if(obj.name && names.length < 120) names.push({name:obj.name,type:obj.type});
      if(!obj.isMesh || !words.test(obj.name))return;
      const geom=obj.geometry,pos=geom?.getAttribute("position"),index=geom?.getIndex();
      if(!pos)return;
      const materials=(Array.isArray(obj.material)?obj.material:[obj.material]).map(m=>({
        name:m?.name,color:m?.color?.getHexString?.(),opacity:m?.opacity
      }));
      const group={
        name:obj.name,vertexCount:pos.count,triangleCount:Math.floor((index?.count??pos.count)/3),
        indexed:!!index,geometryGroups:geom.groups?.length ?? 0,materials,
        patchTriangles:0,patchVertices:0,candidateCrowns:0,components:[],partialComponents:0
      };
      const m=obj.matrixWorld;
      const V=new Float64Array(pos.count*3);
      const v={x:0,y:0,z:0};
      const e=m.elements;
      for(let i=0;i<pos.count;i++){
        const x=pos.getX(i),y=pos.getY(i),z=pos.getZ(i);
        const idx=i*3;
        V[idx]=e[0]*x+e[4]*y+e[8]*z+e[12];
        V[idx+1]=e[1]*x+e[5]*y+e[9]*z+e[13];
        V[idx+2]=e[2]*x+e[6]*y+e[10]*z+e[14];
        if(inPatch(V[idx],V[idx+2]))group.patchVertices++;
      }
      const parent=new Int32Array(pos.count);parent.fill(-1);
      function find(i){let k=i;while(parent[k]!==k){parent[k]=parent[parent[k]];k=parent[k];}return k;}
      function union(a,b){const ra=find(a),rb=find(b);if(ra!==rb)parent[rb]=ra;}
      const faceCount=Math.floor((index?.count??pos.count)/3);
      for(let f=0;f<faceCount;f++){
        const a=index?index.getX(f*3):f*3;
        const b=index?index.getX(f*3+1):f*3+1;
        const c=index?index.getX(f*3+2):f*3+2;
        const x0=V[a*3],z0=V[a*3+2],x1=V[b*3],z1=V[b*3+2],x2=V[c*3],z2=V[c*3+2];
        if(!inPatch(x0,z0)||!inPatch(x1,z1)||!inPatch(x2,z2))continue;
        if(parent[a]<0)parent[a]=a;
        if(parent[b]<0)parent[b]=b;
        if(parent[c]<0)parent[c]=c;
        union(a,b);union(a,c);
        group.patchTriangles++;
      }
      const comps=new Map();
      for(let i=0;i<pos.count;i++){
        if(parent[i]<0)continue;
        const rootId=find(i),x=V[i*3],y=V[i*3+1],z=V[i*3+2];
        let box=comps.get(rootId);
        if(!box){box={min:[x,y,z],max:[x,y,z],vertices:0};comps.set(rootId,box);}
        for(let j=0;j<3;j++){
          const value=V[i*3+j];
          box.min[j]=Math.min(box.min[j],value);
          box.max[j]=Math.max(box.max[j],value);
        }
        box.vertices++;
      }
      group.partialComponents=comps.size;
      group.components=[...comps.values()].filter(b=>{
        const width=b.max[0]-b.min[0],height=b.max[1]-b.min[1],depth=b.max[2]-b.min[2];
        return width>0.8&&depth>0.8&&height>0.5;
      }).map(b=>{
        const centre=b.min.map((v,j)=>(v+b.max[j])/2);
        const scale=b.min.map((v,j)=>b.max[j]-v);
        return {centre:centre.map(n=>+n.toFixed(3)),
          size:scale.map(n=>+n.toFixed(3)),vertices:b.vertices,
          distanceToCamera:+Math.hypot(centre[0]-camera.x,centre[2]-camera.z).toFixed(2)};
      }).sort((a,b)=>a.distanceToCamera-b.distanceToCamera).slice(0,80);
      group.candidateCrowns=group.components.length;
      targets.push(group);
    });
    return {source:"accepted Coimbra 032 GLB",camera:camera.toArray(),
      exporter:three,allNodesSample:names,vegetation:targets,
      qa:globalThis.coimbra037.streetQA.diagnostics(),
      candidate:globalThis.coimbra037.poloVisual.metrics()};
  });
  assert.ok(report.vegetation.length>0,"Source must contain recognized vegetation meshes");
  await writeFile(path.join(dir,"coimbra-041-source-inventory.json"),JSON.stringify({report,errs},null,2)+"\n");
  console.log(JSON.stringify({
    vegetation:report.vegetation.map(x=>({name:x.name,materials:x.materials,patchTriangles:x.patchTriangles,
      components:x.partialComponents,crownCandidates:x.candidateCrowns,closest:x.components.slice(0,8)})),
    nodeCount:report.allNodesSample.length,errors:errs
  },null,2));
} catch(e){
  console.error(e);
  process.exitCode=1;
} finally {
  await browser.close();
}
