import{Gt as e,Kt as t,O as n,Sn as r,Vt as i,Wn as a,Yt as o,Zt as s,b as c,lt as l,mn as u,nn as d,tr as f,ut as p,v as m,wn as h,y as g}from"./Space-n5-XcguU.js";import{r as _}from"./Tag-D1fOKpTH.js";import{a as v,h as y}from"./index-CeE6v959.js";var b=e([e(`@keyframes spin-rotate`,`
 from {
 transform: rotate(0);
 }
 to {
 transform: rotate(360deg);
 }
 `),t(`spin-container`,`
 position: relative;
 `,[t(`spin-body`,`
 position: absolute;
 top: 50%;
 left: 50%;
 transform: translateX(-50%) translateY(-50%);
 `,[m()])]),t(`spin-body`,`
 display: inline-flex;
 align-items: center;
 justify-content: center;
 flex-direction: column;
 `),t(`spin`,`
 display: inline-flex;
 height: var(--n-size);
 width: var(--n-size);
 font-size: var(--n-size);
 color: var(--n-color);
 `,[o(`rotate`,`
 animation: spin-rotate 2s linear infinite;
 `)]),t(`spin-description`,`
 display: inline-block;
 font-size: var(--n-font-size);
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 margin-top: 8px;
 `),t(`spin-content`,`
 opacity: 1;
 transition: opacity .3s var(--n-bezier);
 pointer-events: all;
 `,[o(`spinning`,`
 user-select: none;
 -webkit-user-select: none;
 pointer-events: none;
 opacity: var(--n-opacity-spinning);
 `)])]),x={small:20,medium:18,large:16},S=r({name:`Spin`,props:Object.assign(Object.assign(Object.assign({},n.props),{contentClass:String,contentStyle:[Object,String],description:String,size:{type:[String,Number],default:`medium`},show:{type:Boolean,default:!0},rotate:{type:Boolean,default:!0},spinning:{type:Boolean,validator:()=>!0,default:void 0},delay:Number}),c),slots:Object,setup(e){let{mergedClsPrefixRef:t,inlineThemeDisabled:r}=p(e),o=n(`Spin`,`-spin`,b,y,e,t),c=u(()=>{let{size:t}=e,{common:{cubicBezierEaseInOut:n},self:r}=o.value,{opacitySpinning:a,color:c,textColor:l}=r;return{"--n-bezier":n,"--n-opacity-spinning":a,"--n-size":typeof t==`number`?i(t):r[s(`size`,t)],"--n-color":c,"--n-text-color":l}}),d=r?l(`spin`,u(()=>{let{size:t}=e;return typeof t==`number`?String(t):t[0]}),c,e):void 0,m=_(e,[`spinning`,`show`]),h=f(!1);return a(t=>{let n;if(m.value){let{delay:r}=e;if(r){n=window.setTimeout(()=>{h.value=!0},r),t(()=>{clearTimeout(n)});return}}h.value=m.value}),{mergedClsPrefix:t,active:h,mergedStrokeWidth:u(()=>{let{strokeWidth:t}=e;if(t!==void 0)return t;let{size:n}=e;return x[typeof n==`number`?`medium`:n]}),cssVars:r?void 0:c,themeClass:d?.themeClass,onRender:d?.onRender}},render(){var e;let{$slots:t,mergedClsPrefix:n,description:r}=this,i=t.icon&&this.rotate,a=(r||t.description)&&h(`div`,{class:`${n}-spin-description`},r||t.description?.call(t)),o=t.icon?h(`div`,{class:[`${n}-spin-body`,this.themeClass]},h(`div`,{class:[`${n}-spin`,i&&`${n}-spin--rotate`],style:t.default?``:this.cssVars},t.icon()),a):h(`div`,{class:[`${n}-spin-body`,this.themeClass]},h(g,{clsPrefix:n,style:t.default?``:this.cssVars,stroke:this.stroke,"stroke-width":this.mergedStrokeWidth,radius:this.radius,scale:this.scale,class:`${n}-spin`}),a);return(e=this.onRender)==null||e.call(this),t.default?h(`div`,{class:[`${n}-spin-container`,this.themeClass],style:this.cssVars},h(`div`,{class:[`${n}-spin-content`,this.active&&`${n}-spin-content--spinning`,this.contentClass],style:this.contentStyle},t),h(d,{name:`fade-in-transition`},{default:()=>this.active?o:null})):o}});function C(e){let t=new URLSearchParams;for(let[n,r]of Object.entries(e))r==null||r===``||t.set(n,String(r));return t}var w={schemas:()=>v.get(`/db/schemas`),tables:e=>v.get(`/db/tables/${e}`),rows:(e,t,n)=>{let r=new URLSearchParams;for(let[e,t]of Object.entries(n))t===``||t==null||r.set(e,String(t));return v.get(`/db/tables/${e}/${t}/rows?${r}`)},runSql:(e,t=!0)=>v.post(`/db/sql/execute`,{statement:e,read_only:t}),policies:(e,t)=>v.get(`/db/rls/${e}/${t}`),dryRunPolicy:(e,t)=>v.post(`/db/rls/dry-run`,{ddl:e,sample_query:t}),migrations:()=>v.get(`/db/migrations`)},T={users:e=>v.get(`/auth/users?${C(e)}`),getUser:e=>v.get(`/auth/users/${e}`),banUser:(e,t)=>v.post(`/auth/users/${e}/ban`,t?{duration_seconds:t}:void 0),unbanUser:e=>v.post(`/auth/users/${e}/unban`),forceLogout:e=>v.post(`/auth/users/${e}/force-logout`),refreshTokens:e=>v.get(`/auth/refresh-tokens?${C(e)}`),revokeToken:e=>v.del(`/auth/refresh-tokens/${e}`),audit:e=>v.get(`/auth/audit?${C(e)}`),templates:()=>v.get(`/auth/templates`),updateTemplate:(e,t)=>v.patch(`/auth/templates/${e}`,t),session:()=>v.get(`/auth/session`)},E={buckets:()=>v.get(`/storage/buckets`),objects:(e,t)=>v.get(`/storage/buckets/${e}/objects?${C(t)}`),sign:(e,t,n,r)=>v.post(`/storage/objects/${e}/sign`,{expires_in:t,role:n??`service_role`,impersonate_sub:r||void 0}),deleteObject:e=>v.del(`/storage/objects/${e}`)},D={routes:()=>v.get(`/functions/routes`),source:e=>v.get(`/functions/${encodeURIComponent(e)}/source`),invoke:(e,t)=>v.post(`/functions/${encodeURIComponent(e)}/invoke`,t)},O={tables:()=>v.get(`/realtime/tables`),channels:()=>v.get(`/realtime/channels`),broadcast:(e,t,n)=>v.post(`/realtime/broadcast`,{topic:e,event:t,payload:n})},k={queue:e=>v.get(`/jobs/queue?${C(e)}`),retry:e=>v.post(`/jobs/${e}/retry`),cancel:e=>v.post(`/jobs/${e}/cancel`),crons:()=>v.get(`/jobs/crons`),cronHealth:()=>v.get(`/jobs/crons/health`),runCronNow:e=>v.post(`/jobs/crons/${encodeURIComponent(e)}/run-now`)},A={status:()=>v.get(`/system/status`)},j={backups:e=>v.get(`/ops/backups?${C(e)}`),startBackup:e=>v.post(`/ops/backups`,{kind:e}),downloadUrl:e=>v.get(`/ops/backups/${e}/download`)};export{j as a,A as c,k as i,S as l,w as n,O as o,D as r,E as s,T as t};
//# sourceMappingURL=resources-Bt6thQCD.js.map