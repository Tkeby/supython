import{C as e,Ft as t,Gn as n,Gt as r,In as i,Jt as a,Kt as o,O as s,Sn as c,T as l,Vt as u,Xt as d,Yt as f,Zt as p,_ as m,_t as h,ar as g,bn as _,c as v,ct as y,gn as b,hn as x,lr as S,lt as C,mn as w,mt as T,r as E,sr as D,t as O,tr as k,ur as A,ut as j,vn as M,wn as N,xn as P,xt as F,y as I,zt as L}from"./Space-n5-XcguU.js";import{t as R}from"./Select-DIzZyRZb.js";import{t as z}from"./use-merged-state-BvhkaHNX.js";import{t as B}from"./Tag-D1fOKpTH.js";import{t as V}from"./DataTable-COAAWEft.js";import{l as H,n as U}from"./resources-Bt6thQCD.js";import{c as W,m as G}from"./index-CeE6v959.js";import{n as K,t as q}from"./EmptyState-DeDck-OL.js";import{t as J}from"./useToast-DsZKx0IX.js";import{t as Y}from"./useConfirm-tMjvBFXR.js";import{t as X}from"./SqlEditor-b8pTsILY.js";function Z(e){let{primaryColor:n,opacityDisabled:r,borderRadius:i,textColor3:a}=e;return Object.assign(Object.assign({},G),{iconColor:a,textColor:`white`,loadingColor:n,opacityDisabled:r,railColor:`rgba(0, 0, 0, .14)`,railColorActive:n,buttonBoxShadow:`0 1px 4px 0 rgba(0, 0, 0, 0.3), inset 0 0 1px 0 rgba(0, 0, 0, 0.05)`,buttonColor:`#FFF`,railBorderRadiusSmall:i,railBorderRadiusMedium:i,railBorderRadiusLarge:i,buttonBorderRadiusSmall:i,buttonBorderRadiusMedium:i,buttonBorderRadiusLarge:i,boxShadowFocus:`0 0 0 2px ${t(n,{alpha:.2})}`})}var Q={name:`Switch`,common:m,self:Z},ee=o(`switch`,`
 height: var(--n-height);
 min-width: var(--n-width);
 vertical-align: middle;
 user-select: none;
 -webkit-user-select: none;
 display: inline-flex;
 outline: none;
 justify-content: center;
 align-items: center;
`,[a(`children-placeholder`,`
 height: var(--n-rail-height);
 display: flex;
 flex-direction: column;
 overflow: hidden;
 pointer-events: none;
 visibility: hidden;
 `),a(`rail-placeholder`,`
 display: flex;
 flex-wrap: none;
 `),a(`button-placeholder`,`
 width: calc(1.75 * var(--n-rail-height));
 height: var(--n-rail-height);
 `),o(`base-loading`,`
 position: absolute;
 top: 50%;
 left: 50%;
 transform: translateX(-50%) translateY(-50%);
 font-size: calc(var(--n-button-width) - 4px);
 color: var(--n-loading-color);
 transition: color .3s var(--n-bezier);
 `,[e({left:`50%`,top:`50%`,originalTransform:`translateX(-50%) translateY(-50%)`})]),a(`checked, unchecked`,`
 transition: color .3s var(--n-bezier);
 color: var(--n-text-color);
 box-sizing: border-box;
 position: absolute;
 white-space: nowrap;
 top: 0;
 bottom: 0;
 display: flex;
 align-items: center;
 line-height: 1;
 `),a(`checked`,`
 right: 0;
 padding-right: calc(1.25 * var(--n-rail-height) - var(--n-offset));
 `),a(`unchecked`,`
 left: 0;
 justify-content: flex-end;
 padding-left: calc(1.25 * var(--n-rail-height) - var(--n-offset));
 `),r(`&:focus`,[a(`rail`,`
 box-shadow: var(--n-box-shadow-focus);
 `)]),f(`round`,[a(`rail`,`border-radius: calc(var(--n-rail-height) / 2);`,[a(`button`,`border-radius: calc(var(--n-button-height) / 2);`)])]),d(`disabled`,[d(`icon`,[f(`rubber-band`,[f(`pressed`,[a(`rail`,[a(`button`,`max-width: var(--n-button-width-pressed);`)])]),a(`rail`,[r(`&:active`,[a(`button`,`max-width: var(--n-button-width-pressed);`)])]),f(`active`,[f(`pressed`,[a(`rail`,[a(`button`,`left: calc(100% - var(--n-offset) - var(--n-button-width-pressed));`)])]),a(`rail`,[r(`&:active`,[a(`button`,`left: calc(100% - var(--n-offset) - var(--n-button-width-pressed));`)])])])])])]),f(`active`,[a(`rail`,[a(`button`,`left: calc(100% - var(--n-button-width) - var(--n-offset))`)])]),a(`rail`,`
 overflow: hidden;
 height: var(--n-rail-height);
 min-width: var(--n-rail-width);
 border-radius: var(--n-rail-border-radius);
 cursor: pointer;
 position: relative;
 transition:
 opacity .3s var(--n-bezier),
 background .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 background-color: var(--n-rail-color);
 `,[a(`button-icon`,`
 color: var(--n-icon-color);
 transition: color .3s var(--n-bezier);
 font-size: calc(var(--n-button-height) - 4px);
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 display: flex;
 justify-content: center;
 align-items: center;
 line-height: 1;
 `,[e()]),a(`button`,`
 align-items: center; 
 top: var(--n-offset);
 left: var(--n-offset);
 height: var(--n-button-height);
 width: var(--n-button-width-pressed);
 max-width: var(--n-button-width);
 border-radius: var(--n-button-border-radius);
 background-color: var(--n-button-color);
 box-shadow: var(--n-button-box-shadow);
 box-sizing: border-box;
 cursor: inherit;
 content: "";
 position: absolute;
 transition:
 background-color .3s var(--n-bezier),
 left .3s var(--n-bezier),
 opacity .3s var(--n-bezier),
 max-width .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 `)]),f(`active`,[a(`rail`,`background-color: var(--n-rail-color-active);`)]),f(`loading`,[a(`rail`,`
 cursor: wait;
 `)]),f(`disabled`,[a(`rail`,`
 cursor: not-allowed;
 opacity: .5;
 `)])]),te=Object.assign(Object.assign({},s.props),{size:String,value:{type:[String,Number,Boolean],default:void 0},loading:Boolean,defaultValue:{type:[String,Number,Boolean],default:!1},disabled:{type:Boolean,default:void 0},round:{type:Boolean,default:!0},"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array],checkedValue:{type:[String,Number,Boolean],default:!0},uncheckedValue:{type:[String,Number,Boolean],default:!1},railStyle:Function,rubberBand:{type:Boolean,default:!0},spinProps:Object,onChange:[Function,Array]}),$,ne=c({name:`Switch`,props:te,slots:Object,setup(e){$===void 0&&($=typeof CSS<`u`?CSS.supports===void 0?!1:CSS.supports(`width`,`max(1px)`):!0);let{mergedClsPrefixRef:t,inlineThemeDisabled:n,mergedComponentPropsRef:r}=j(e),i=s(`Switch`,`-switch`,ee,Q,e,t),a=y(e,{mergedSize(t){return e.size===void 0?t?t.mergedSize.value:r?.value?.Switch?.size||`medium`:e.size}}),{mergedSizeRef:o,mergedDisabledRef:c}=a,l=k(e.defaultValue),d=z(g(e,`value`),l),f=w(()=>d.value===e.checkedValue),m=k(!1),h=k(!1),_=w(()=>{let{railStyle:t}=e;if(t)return t({focused:h.value,checked:f.value})});function v(t){let{"onUpdate:value":n,onChange:r,onUpdateValue:i}=e,{nTriggerFormInput:o,nTriggerFormChange:s}=a;n&&F(n,t),i&&F(i,t),r&&F(r,t),l.value=t,o(),s()}function b(){let{nTriggerFormFocus:e}=a;e()}function x(){let{nTriggerFormBlur:e}=a;e()}function S(){e.loading||c.value||(d.value===e.checkedValue?v(e.uncheckedValue):v(e.checkedValue))}function T(){h.value=!0,b()}function E(){h.value=!1,x(),m.value=!1}function D(t){e.loading||c.value||t.key===` `&&(d.value===e.checkedValue?v(e.uncheckedValue):v(e.checkedValue),m.value=!1)}function O(t){e.loading||c.value||t.key===` `&&(t.preventDefault(),m.value=!0)}let A=w(()=>{let{value:e}=o,{self:{opacityDisabled:t,railColor:n,railColorActive:r,buttonBoxShadow:a,buttonColor:s,boxShadowFocus:c,loadingColor:l,textColor:d,iconColor:f,[p(`buttonHeight`,e)]:m,[p(`buttonWidth`,e)]:h,[p(`buttonWidthPressed`,e)]:g,[p(`railHeight`,e)]:_,[p(`railWidth`,e)]:v,[p(`railBorderRadius`,e)]:y,[p(`buttonBorderRadius`,e)]:b},common:{cubicBezierEaseInOut:x}}=i.value,S,C,w;return $?(S=`calc((${_} - ${m}) / 2)`,C=`max(${_}, ${m})`,w=`max(${v}, calc(${v} + ${m} - ${_}))`):(S=u((L(_)-L(m))/2),C=u(Math.max(L(_),L(m))),w=L(_)>L(m)?v:u(L(v)+L(m)-L(_))),{"--n-bezier":x,"--n-button-border-radius":b,"--n-button-box-shadow":a,"--n-button-color":s,"--n-button-width":h,"--n-button-width-pressed":g,"--n-button-height":m,"--n-height":C,"--n-offset":S,"--n-opacity-disabled":t,"--n-rail-border-radius":y,"--n-rail-color":n,"--n-rail-color-active":r,"--n-rail-height":_,"--n-rail-width":v,"--n-width":w,"--n-box-shadow-focus":c,"--n-loading-color":l,"--n-text-color":d,"--n-icon-color":f}}),M=n?C(`switch`,w(()=>o.value[0]),A,e):void 0;return{handleClick:S,handleBlur:E,handleFocus:T,handleKeyup:D,handleKeydown:O,mergedRailStyle:_,pressed:m,mergedClsPrefix:t,mergedValue:d,checked:f,mergedDisabled:c,cssVars:n?void 0:A,themeClass:M?.themeClass,onRender:M?.onRender}},render(){let{mergedClsPrefix:e,mergedDisabled:t,checked:n,mergedRailStyle:r,onRender:i,$slots:a}=this;i?.();let{checked:o,unchecked:s,icon:c,"checked-icon":u,"unchecked-icon":d}=a,f=!(T(c)&&T(u)&&T(d));return N(`div`,{role:`switch`,"aria-checked":n,class:[`${e}-switch`,this.themeClass,f&&`${e}-switch--icon`,n&&`${e}-switch--active`,t&&`${e}-switch--disabled`,this.round&&`${e}-switch--round`,this.loading&&`${e}-switch--loading`,this.pressed&&`${e}-switch--pressed`,this.rubberBand&&`${e}-switch--rubber-band`],tabindex:this.mergedDisabled?void 0:0,style:this.cssVars,onClick:this.handleClick,onFocus:this.handleFocus,onBlur:this.handleBlur,onKeyup:this.handleKeyup,onKeydown:this.handleKeydown},N(`div`,{class:`${e}-switch__rail`,"aria-hidden":`true`,style:r},h(o,t=>h(s,n=>t||n?N(`div`,{"aria-hidden":!0,class:`${e}-switch__children-placeholder`},N(`div`,{class:`${e}-switch__rail-placeholder`},N(`div`,{class:`${e}-switch__button-placeholder`}),t),N(`div`,{class:`${e}-switch__rail-placeholder`},N(`div`,{class:`${e}-switch__button-placeholder`}),n)):null)),N(`div`,{class:`${e}-switch__button`},h(c,t=>h(u,n=>h(d,r=>N(l,null,{default:()=>this.loading?N(I,Object.assign({key:`loading`,clsPrefix:e,strokeWidth:20},this.spinProps)):this.checked&&(n||t)?N(`div`,{class:`${e}-switch__button-icon`,key:n?`checked-icon`:`icon`},n||t):!this.checked&&(r||t)?N(`div`,{class:`${e}-switch__button-icon`,key:r?`unchecked-icon`:`icon`},r||t):null})))),h(o,t=>t&&N(`div`,{key:`checked`,class:`${e}-switch__checked`},t)),h(s,t=>t&&N(`div`,{key:`unchecked`,class:`${e}-switch__unchecked`},t)))))}}),re={key:1},ie=c({__name:`SqlWorkspace`,setup(e){let t=Y(),r=J(),a=k(``),o=k(!0),s=k(!1),c=k(null),l=k(null),u=k([]),d=k(null),f=w(()=>u.value.map((e,t)=>({label:`${e.label} \u2014 ${new Date(e.at).toLocaleTimeString()}`,value:String(t)})));function p(e){let t=e.trim();if(!t||u.value[0]?.value===t)return;let n=t.split(`
`)[0].slice(0,60)||t.slice(0,60);u.value.unshift({label:n,value:t,at:Date.now()}),u.value.length>20&&u.value.pop()}function m(e){let t=parseInt(e,10),n=u.value[t];n&&(a.value=n.value)}async function h(e){if(!e&&!await t(`Enable write mode?`,`You are about to allow INSERT, UPDATE, DELETE and DDL. Changes commit immediately. Continue?`)){o.value=!0;return}o.value=e}async function g(){let e=a.value.trim();if(!e){r.warning(`Enter a SQL statement`);return}s.value=!0,c.value=null,l.value=null;try{let t=await U.runSql(e,o.value);c.value=t,p(e),r.success(`${t.row_count} row${t.row_count===1?``:`s`}`)}catch(e){l.value=e.message??`Query failed`,r.error(l.value)}finally{s.value=!1}}let y=w(()=>c.value?c.value.columns.map(e=>({title:e,key:e})):[]),C=w(()=>c.value?c.value.rows.map(e=>Object.fromEntries(c.value.columns.map((t,n)=>{let r=e[n],i;return i=r===null?`null`:typeof r==`object`?JSON.stringify(r):String(r),[t,i]}))):[]);return(e,t)=>(i(),b(D(E),{title:`SQL Workspace`},{default:n(()=>[P(D(O),{vertical:``,size:16},{default:n(()=>[P(D(O),{align:`center`,justify:`space-between`},{default:n(()=>[P(D(O),{align:`center`,size:12},{default:n(()=>[P(D(R),{value:d.value,"onUpdate:value":[t[0]||=e=>d.value=e,m],options:f.value,placeholder:`History`,clearable:``,style:{width:`260px`}},null,8,[`value`,`options`]),P(D(v),{type:`primary`,loading:s.value,onClick:g},{default:n(()=>[...t[2]||=[_(` Run `,-1)]]),_:1},8,[`loading`]),o.value?(i(),b(D(B),{key:0,type:`default`,size:`small`},{default:n(()=>[...t[3]||=[_(`Read-only`,-1)]]),_:1})):(i(),b(D(B),{key:1,type:`warning`,size:`small`},{default:n(()=>[...t[4]||=[_(`Write enabled`,-1)]]),_:1}))]),_:1}),P(D(O),{align:`center`,size:8},{default:n(()=>[P(D(W),{depth:`3`,style:{"font-size":`12px`}},{default:n(()=>[...t[5]||=[_(`Read-only`,-1)]]),_:1}),P(D(ne),{value:o.value,round:!1,"onUpdate:value":h},{"checked-icon":n(()=>[...t[6]||=[x(`svg`,{width:`14`,height:`14`,viewBox:`0 0 24 24`,fill:`none`,stroke:`currentColor`,"stroke-width":`3`},[x(`rect`,{x:`3`,y:`11`,width:`18`,height:`11`,rx:`2`}),x(`path`,{d:`M7 11V7a5 5 0 0110 0v4`})],-1)]]),"unchecked-icon":n(()=>[...t[7]||=[x(`svg`,{width:`14`,height:`14`,viewBox:`0 0 24 24`,fill:`none`,stroke:`currentColor`,"stroke-width":`3`},[x(`path`,{d:`M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z`}),x(`line`,{x1:`12`,y1:`9`,x2:`12`,y2:`13`}),x(`line`,{x1:`12`,y1:`17`,x2:`12.01`,y2:`17`})],-1)]]),_:1},8,[`value`])]),_:1})]),_:1}),P(X,{modelValue:a.value,"onUpdate:modelValue":t[1]||=e=>a.value=e,height:`280px`,"on-run":g,style:S(o.value?{}:{border:`1px solid var(--n-warning-color)`})},null,8,[`modelValue`,`style`]),P(D(H),{show:s.value},{default:n(()=>[l.value?(i(),b(K,{key:0,error:{message:l.value},retry:g},null,8,[`error`])):c.value?(i(),M(`div`,re,[P(D(O),{align:`center`,size:8,style:{"margin-bottom":`8px`}},{default:n(()=>[P(D(W),{depth:`3`,style:{"font-size":`12px`}},{default:n(()=>[_(A(c.value.row_count)+` row`+A(c.value.row_count===1?``:`s`),1)]),_:1})]),_:1}),C.value.length?(i(),b(D(V),{key:0,columns:y.value,data:C.value,bordered:!1,size:`small`,"scroll-x":600},null,8,[`columns`,`data`])):(i(),b(q,{key:1,description:`Query executed successfully. No rows returned.`}))])):(i(),b(q,{key:2,description:`Write a SQL query and press Run (Ctrl+Enter) to see results.`}))]),_:1},8,[`show`])]),_:1})]),_:1}))}});export{ie as default};
//# sourceMappingURL=SqlWorkspace-BUS7IntH.js.map