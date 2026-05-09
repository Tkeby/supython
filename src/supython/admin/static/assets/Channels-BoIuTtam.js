import{$ as e,At as t,Bt as n,Dt as r,E as i,En as a,Fn as o,Gn as s,Gt as c,In as l,Jt as u,Kn as d,Kt as f,Ln as p,O as m,On as h,Pn as g,Rn as _,S as v,Sn as y,St as b,Tt as x,Un as S,Wn as ee,Xt as C,Yt as w,Zt as T,_n as E,_t as D,ar as O,bn as k,bt as A,c as j,gn as M,hn as N,kn as P,lt as te,mn as F,nt as ne,on as I,ot as L,pn as R,r as re,rn as ie,rr as ae,sn as z,sr as B,t as V,tr as H,un as oe,ur as U,ut as se,vn as W,wn as G,xn as K,xt as q,zt as ce}from"./Space-n5-XcguU.js";import{A as J,H as le,k as Y,v as ue}from"./Select-DIzZyRZb.js";import{t as de}from"./Input-DppYTq9C.js";import{t as fe}from"./use-merged-state-BvhkaHNX.js";import{r as pe,t as X}from"./Tag-D1fOKpTH.js";import{t as me}from"./DataTable-COAAWEft.js";import{l as he,o as ge}from"./resources-Bt6thQCD.js";import{R as Z,c as Q,p as _e}from"./index-CeE6v959.js";import{t as ve}from"./useResource-C_rJCY8C.js";import{n as ye,t as $}from"./EmptyState-DeDck-OL.js";import{t as be}from"./JsonField-DibyJgun.js";var xe=Y(`.v-x-scroll`,{overflow:`auto`,scrollbarWidth:`none`},[Y(`&::-webkit-scrollbar`,{width:0,height:0})]),Se=y({name:`XScroll`,props:{disabled:Boolean,onScroll:Function},setup(){let e=H(null);function t(e){!(e.currentTarget.offsetWidth<e.currentTarget.scrollWidth)||e.deltaY===0||(e.currentTarget.scrollLeft+=e.deltaY+e.deltaX,e.preventDefault())}let n=r();return xe.mount({id:`vueuc/x-scroll`,head:!0,anchorMetaName:J,ssr:n}),Object.assign({selfRef:e,handleWheel:t},{scrollTo(...t){var n;(n=e.value)==null||n.scrollTo(...t)}})},render(){return G(`div`,{ref:`selfRef`,onScroll:this.onScroll,onWheel:this.disabled?void 0:this.handleWheel,class:`v-x-scroll`},this.$slots)}}),Ce=/\s/;function we(e){for(var t=e.length;t--&&Ce.test(e.charAt(t)););return t}var Te=/^\s+/;function Ee(e){return e&&e.slice(0,we(e)+1).replace(Te,``)}var De=NaN,Oe=/^[-+]0x[0-9a-f]+$/i,ke=/^0b[01]+$/i,Ae=/^0o[0-7]+$/i,je=parseInt;function Me(t){if(typeof t==`number`)return t;if(ne(t))return De;if(e(t)){var n=typeof t.valueOf==`function`?t.valueOf():t;t=e(n)?n+``:n}if(typeof t!=`string`)return t===0?t:+t;t=Ee(t);var r=ke.test(t);return r||Ae.test(t)?je(t.slice(2),r?2:8):Oe.test(t)?De:+t}var Ne=function(){return L.Date.now()},Pe=`Expected a function`,Fe=Math.max,Ie=Math.min;function Le(t,n,r){var i,a,o,s,c,l,u=0,d=!1,f=!1,p=!0;if(typeof t!=`function`)throw TypeError(Pe);n=Me(n)||0,e(r)&&(d=!!r.leading,f=`maxWait`in r,o=f?Fe(Me(r.maxWait)||0,n):o,p=`trailing`in r?!!r.trailing:p);function m(e){var n=i,r=a;return i=a=void 0,u=e,s=t.apply(r,n),s}function h(e){return u=e,c=setTimeout(v,n),d?m(e):s}function g(e){var t=e-l,r=e-u,i=n-t;return f?Ie(i,o-r):i}function _(e){var t=e-l,r=e-u;return l===void 0||t>=n||t<0||f&&r>=o}function v(){var e=Ne();if(_(e))return y(e);c=setTimeout(v,g(e))}function y(e){return c=void 0,p&&i?m(e):(i=a=void 0,s)}function b(){c!==void 0&&clearTimeout(c),u=0,i=l=a=c=void 0}function x(){return c===void 0?s:y(Ne())}function S(){var e=Ne(),t=_(e);if(i=arguments,a=this,l=e,t){if(c===void 0)return h(l);if(f)return clearTimeout(c),c=setTimeout(v,n),m(l)}return c===void 0&&(c=setTimeout(v,n)),s}return S.cancel=b,S.flush=x,S}var Re=`Expected a function`;function ze(t,n,r){var i=!0,a=!0;if(typeof t!=`function`)throw TypeError(Re);return e(r)&&(i=`leading`in r?!!r.leading:i,a=`trailing`in r?!!r.trailing:a),Le(t,n,{leading:i,maxWait:n,trailing:a})}var Be=y({name:`Add`,render(){return G(`svg`,{width:`512`,height:`512`,viewBox:`0 0 512 512`,fill:`none`,xmlns:`http://www.w3.org/2000/svg`},G(`path`,{d:`M256 112V400M400 256H112`,stroke:`currentColor`,"stroke-width":`32`,"stroke-linecap":`round`,"stroke-linejoin":`round`}))}}),Ve=t(`n-tabs`),He={tab:[String,Number,Object,Function],name:{type:[String,Number],required:!0},disabled:Boolean,displayDirective:{type:String,default:`if`},closable:{type:Boolean,default:void 0},tabProps:Object,label:[String,Number,Object,Function]},Ue=y({__TAB_PANE__:!0,name:`TabPane`,alias:[`TabPanel`],props:He,slots:Object,setup(e){let t=a(Ve,null);return t||b(`tab-pane`,"`n-tab-pane` must be placed inside `n-tabs`."),{style:t.paneStyleRef,class:t.paneClassRef,mergedClsPrefix:t.mergedClsPrefixRef}},render(){return G(`div`,{class:[`${this.mergedClsPrefix}-tab-pane`,this.class],style:this.style},this.$slots)}}),We=y({__TAB__:!0,inheritAttrs:!1,name:`Tab`,props:Object.assign({internalLeftPadded:Boolean,internalAddable:Boolean,internalCreatedByPane:Boolean},Z(He,[`displayDirective`])),setup(e){let{mergedClsPrefixRef:t,valueRef:n,typeRef:r,closableRef:i,tabStyleRef:o,addTabStyleRef:s,tabClassRef:c,addTabClassRef:l,tabChangeIdRef:u,onBeforeLeaveRef:d,triggerRef:f,handleAdd:p,activateTab:m,handleClose:h}=a(Ve);return{trigger:f,mergedClosable:F(()=>{if(e.internalAddable)return!1;let{closable:t}=e;return t===void 0?i.value:t}),style:o,addStyle:s,tabClass:c,addTabClass:l,clsPrefix:t,value:n,type:r,handleClose(t){t.stopPropagation(),!e.disabled&&h(e.name)},activateTab(){if(e.disabled)return;if(e.internalAddable){p();return}let{name:t}=e,r=++u.id;if(t!==n.value){let{value:i}=d;i?Promise.resolve(i(e.name,n.value)).then(e=>{e&&u.id===r&&m(t)}):m(t)}}}},render(){let{internalAddable:e,clsPrefix:t,name:n,disabled:r,label:a,tab:o,value:s,mergedClosable:c,trigger:l,$slots:{default:u}}=this,d=a??o;return G(`div`,{class:`${t}-tabs-tab-wrapper`},this.internalLeftPadded?G(`div`,{class:`${t}-tabs-tab-pad`}):null,G(`div`,Object.assign({key:n,"data-name":n,"data-disabled":r?!0:void 0},h({class:[`${t}-tabs-tab`,s===n&&`${t}-tabs-tab--active`,r&&`${t}-tabs-tab--disabled`,c&&`${t}-tabs-tab--closable`,e&&`${t}-tabs-tab--addable`,e?this.addTabClass:this.tabClass],onClick:l===`click`?this.activateTab:void 0,onMouseenter:l===`hover`?this.activateTab:void 0,style:e?this.addStyle:this.style},this.internalCreatedByPane?this.tabProps||{}:this.$attrs)),G(`span`,{class:`${t}-tabs-tab__label`},e?G(oe,null,G(`div`,{class:`${t}-tabs-tab__height-placeholder`},`\xA0`),G(i,{clsPrefix:t},{default:()=>G(Be,null)})):u?u():typeof d==`object`?d:ue(d??n)),c&&this.type===`card`?G(v,{clsPrefix:t,class:`${t}-tabs-tab__close`,onClick:this.handleClose,disabled:r}):null))}}),Ge=f(`tabs`,`
 box-sizing: border-box;
 width: 100%;
 display: flex;
 flex-direction: column;
 transition:
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
`,[w(`segment-type`,[f(`tabs-rail`,[c(`&.transition-disabled`,[f(`tabs-capsule`,`
 transition: none;
 `)])])]),w(`top`,[f(`tab-pane`,`
 padding: var(--n-pane-padding-top) var(--n-pane-padding-right) var(--n-pane-padding-bottom) var(--n-pane-padding-left);
 `)]),w(`left`,[f(`tab-pane`,`
 padding: var(--n-pane-padding-right) var(--n-pane-padding-bottom) var(--n-pane-padding-left) var(--n-pane-padding-top);
 `)]),w(`left, right`,`
 flex-direction: row;
 `,[f(`tabs-bar`,`
 width: 2px;
 right: 0;
 transition:
 top .2s var(--n-bezier),
 max-height .2s var(--n-bezier),
 background-color .3s var(--n-bezier);
 `),f(`tabs-tab`,`
 padding: var(--n-tab-padding-vertical); 
 `)]),w(`right`,`
 flex-direction: row-reverse;
 `,[f(`tab-pane`,`
 padding: var(--n-pane-padding-left) var(--n-pane-padding-top) var(--n-pane-padding-right) var(--n-pane-padding-bottom);
 `),f(`tabs-bar`,`
 left: 0;
 `)]),w(`bottom`,`
 flex-direction: column-reverse;
 justify-content: flex-end;
 `,[f(`tab-pane`,`
 padding: var(--n-pane-padding-bottom) var(--n-pane-padding-right) var(--n-pane-padding-top) var(--n-pane-padding-left);
 `),f(`tabs-bar`,`
 top: 0;
 `)]),f(`tabs-rail`,`
 position: relative;
 padding: 3px;
 border-radius: var(--n-tab-border-radius);
 width: 100%;
 background-color: var(--n-color-segment);
 transition: background-color .3s var(--n-bezier);
 display: flex;
 align-items: center;
 `,[f(`tabs-capsule`,`
 border-radius: var(--n-tab-border-radius);
 position: absolute;
 pointer-events: none;
 background-color: var(--n-tab-color-segment);
 box-shadow: 0 1px 3px 0 rgba(0, 0, 0, .08);
 transition: transform 0.3s var(--n-bezier);
 `),f(`tabs-tab-wrapper`,`
 flex-basis: 0;
 flex-grow: 1;
 display: flex;
 align-items: center;
 justify-content: center;
 `,[f(`tabs-tab`,`
 overflow: hidden;
 border-radius: var(--n-tab-border-radius);
 width: 100%;
 display: flex;
 align-items: center;
 justify-content: center;
 `,[w(`active`,`
 font-weight: var(--n-font-weight-strong);
 color: var(--n-tab-text-color-active);
 `),c(`&:hover`,`
 color: var(--n-tab-text-color-hover);
 `)])])]),w(`flex`,[f(`tabs-nav`,`
 width: 100%;
 position: relative;
 `,[f(`tabs-wrapper`,`
 width: 100%;
 `,[f(`tabs-tab`,`
 margin-right: 0;
 `)])])]),f(`tabs-nav`,`
 box-sizing: border-box;
 line-height: 1.5;
 display: flex;
 transition: border-color .3s var(--n-bezier);
 `,[u(`prefix, suffix`,`
 display: flex;
 align-items: center;
 `),u(`prefix`,`padding-right: 16px;`),u(`suffix`,`padding-left: 16px;`)]),w(`top, bottom`,[c(`>`,[f(`tabs-nav`,[f(`tabs-nav-scroll-wrapper`,[c(`&::before`,`
 top: 0;
 bottom: 0;
 left: 0;
 width: 20px;
 `),c(`&::after`,`
 top: 0;
 bottom: 0;
 right: 0;
 width: 20px;
 `),w(`shadow-start`,[c(`&::before`,`
 box-shadow: inset 10px 0 8px -8px rgba(0, 0, 0, .12);
 `)]),w(`shadow-end`,[c(`&::after`,`
 box-shadow: inset -10px 0 8px -8px rgba(0, 0, 0, .12);
 `)])])])])]),w(`left, right`,[f(`tabs-nav-scroll-content`,`
 flex-direction: column;
 `),c(`>`,[f(`tabs-nav`,[f(`tabs-nav-scroll-wrapper`,[c(`&::before`,`
 top: 0;
 left: 0;
 right: 0;
 height: 20px;
 `),c(`&::after`,`
 bottom: 0;
 left: 0;
 right: 0;
 height: 20px;
 `),w(`shadow-start`,[c(`&::before`,`
 box-shadow: inset 0 10px 8px -8px rgba(0, 0, 0, .12);
 `)]),w(`shadow-end`,[c(`&::after`,`
 box-shadow: inset 0 -10px 8px -8px rgba(0, 0, 0, .12);
 `)])])])])]),f(`tabs-nav-scroll-wrapper`,`
 flex: 1;
 position: relative;
 overflow: hidden;
 `,[f(`tabs-nav-y-scroll`,`
 height: 100%;
 width: 100%;
 overflow-y: auto; 
 scrollbar-width: none;
 `,[c(`&::-webkit-scrollbar, &::-webkit-scrollbar-track-piece, &::-webkit-scrollbar-thumb`,`
 width: 0;
 height: 0;
 display: none;
 `)]),c(`&::before, &::after`,`
 transition: box-shadow .3s var(--n-bezier);
 pointer-events: none;
 content: "";
 position: absolute;
 z-index: 1;
 `)]),f(`tabs-nav-scroll-content`,`
 display: flex;
 position: relative;
 min-width: 100%;
 min-height: 100%;
 width: fit-content;
 box-sizing: border-box;
 `),f(`tabs-wrapper`,`
 display: inline-flex;
 flex-wrap: nowrap;
 position: relative;
 `),f(`tabs-tab-wrapper`,`
 display: flex;
 flex-wrap: nowrap;
 flex-shrink: 0;
 flex-grow: 0;
 `),f(`tabs-tab`,`
 cursor: pointer;
 white-space: nowrap;
 flex-wrap: nowrap;
 display: inline-flex;
 align-items: center;
 color: var(--n-tab-text-color);
 font-size: var(--n-tab-font-size);
 background-clip: padding-box;
 padding: var(--n-tab-padding);
 transition:
 box-shadow .3s var(--n-bezier),
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[w(`disabled`,{cursor:`not-allowed`}),u(`close`,`
 margin-left: 6px;
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `),u(`label`,`
 display: flex;
 align-items: center;
 z-index: 1;
 `)]),f(`tabs-bar`,`
 position: absolute;
 bottom: 0;
 height: 2px;
 border-radius: 1px;
 background-color: var(--n-bar-color);
 transition:
 left .2s var(--n-bezier),
 max-width .2s var(--n-bezier),
 opacity .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 `,[c(`&.transition-disabled`,`
 transition: none;
 `),w(`disabled`,`
 background-color: var(--n-tab-text-color-disabled)
 `)]),f(`tabs-pane-wrapper`,`
 position: relative;
 overflow: hidden;
 transition: max-height .2s var(--n-bezier);
 `),f(`tab-pane`,`
 color: var(--n-pane-text-color);
 width: 100%;
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 opacity .2s var(--n-bezier);
 left: 0;
 right: 0;
 top: 0;
 `,[c(`&.next-transition-leave-active, &.prev-transition-leave-active, &.next-transition-enter-active, &.prev-transition-enter-active`,`
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 transform .2s var(--n-bezier),
 opacity .2s var(--n-bezier);
 `),c(`&.next-transition-leave-active, &.prev-transition-leave-active`,`
 position: absolute;
 `),c(`&.next-transition-enter-from, &.prev-transition-leave-to`,`
 transform: translateX(32px);
 opacity: 0;
 `),c(`&.next-transition-leave-to, &.prev-transition-enter-from`,`
 transform: translateX(-32px);
 opacity: 0;
 `),c(`&.next-transition-leave-from, &.next-transition-enter-to, &.prev-transition-leave-from, &.prev-transition-enter-to`,`
 transform: translateX(0);
 opacity: 1;
 `)]),f(`tabs-tab-pad`,`
 box-sizing: border-box;
 width: var(--n-tab-gap);
 flex-grow: 0;
 flex-shrink: 0;
 `),w(`line-type, bar-type`,[f(`tabs-tab`,`
 font-weight: var(--n-tab-font-weight);
 box-sizing: border-box;
 vertical-align: bottom;
 `,[c(`&:hover`,{color:`var(--n-tab-text-color-hover)`}),w(`active`,`
 color: var(--n-tab-text-color-active);
 font-weight: var(--n-tab-font-weight-active);
 `),w(`disabled`,{color:`var(--n-tab-text-color-disabled)`})])]),f(`tabs-nav`,[w(`line-type`,[w(`top`,[u(`prefix, suffix`,`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),f(`tabs-nav-scroll-content`,`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),f(`tabs-bar`,`
 bottom: -1px;
 `)]),w(`left`,[u(`prefix, suffix`,`
 border-right: 1px solid var(--n-tab-border-color);
 `),f(`tabs-nav-scroll-content`,`
 border-right: 1px solid var(--n-tab-border-color);
 `),f(`tabs-bar`,`
 right: -1px;
 `)]),w(`right`,[u(`prefix, suffix`,`
 border-left: 1px solid var(--n-tab-border-color);
 `),f(`tabs-nav-scroll-content`,`
 border-left: 1px solid var(--n-tab-border-color);
 `),f(`tabs-bar`,`
 left: -1px;
 `)]),w(`bottom`,[u(`prefix, suffix`,`
 border-top: 1px solid var(--n-tab-border-color);
 `),f(`tabs-nav-scroll-content`,`
 border-top: 1px solid var(--n-tab-border-color);
 `),f(`tabs-bar`,`
 top: -1px;
 `)]),u(`prefix, suffix`,`
 transition: border-color .3s var(--n-bezier);
 `),f(`tabs-nav-scroll-content`,`
 transition: border-color .3s var(--n-bezier);
 `),f(`tabs-bar`,`
 border-radius: 0;
 `)]),w(`card-type`,[u(`prefix, suffix`,`
 transition: border-color .3s var(--n-bezier);
 `),f(`tabs-pad`,`
 flex-grow: 1;
 transition: border-color .3s var(--n-bezier);
 `),f(`tabs-tab-pad`,`
 transition: border-color .3s var(--n-bezier);
 `),f(`tabs-tab`,`
 font-weight: var(--n-tab-font-weight);
 border: 1px solid var(--n-tab-border-color);
 background-color: var(--n-tab-color);
 box-sizing: border-box;
 position: relative;
 vertical-align: bottom;
 display: flex;
 justify-content: space-between;
 font-size: var(--n-tab-font-size);
 color: var(--n-tab-text-color);
 `,[w(`addable`,`
 padding-left: 8px;
 padding-right: 8px;
 font-size: 16px;
 justify-content: center;
 `,[u(`height-placeholder`,`
 width: 0;
 font-size: var(--n-tab-font-size);
 `),C(`disabled`,[c(`&:hover`,`
 color: var(--n-tab-text-color-hover);
 `)])]),w(`closable`,`padding-right: 8px;`),w(`active`,`
 background-color: #0000;
 font-weight: var(--n-tab-font-weight-active);
 color: var(--n-tab-text-color-active);
 `),w(`disabled`,`color: var(--n-tab-text-color-disabled);`)])]),w(`left, right`,`
 flex-direction: column; 
 `,[u(`prefix, suffix`,`
 padding: var(--n-tab-padding-vertical);
 `),f(`tabs-wrapper`,`
 flex-direction: column;
 `),f(`tabs-tab-wrapper`,`
 flex-direction: column;
 `,[f(`tabs-tab-pad`,`
 height: var(--n-tab-gap-vertical);
 width: 100%;
 `)])]),w(`top`,[w(`card-type`,[f(`tabs-scroll-padding`,`border-bottom: 1px solid var(--n-tab-border-color);`),u(`prefix, suffix`,`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),f(`tabs-tab`,`
 border-top-left-radius: var(--n-tab-border-radius);
 border-top-right-radius: var(--n-tab-border-radius);
 `,[w(`active`,`
 border-bottom: 1px solid #0000;
 `)]),f(`tabs-tab-pad`,`
 border-bottom: 1px solid var(--n-tab-border-color);
 `),f(`tabs-pad`,`
 border-bottom: 1px solid var(--n-tab-border-color);
 `)])]),w(`left`,[w(`card-type`,[f(`tabs-scroll-padding`,`border-right: 1px solid var(--n-tab-border-color);`),u(`prefix, suffix`,`
 border-right: 1px solid var(--n-tab-border-color);
 `),f(`tabs-tab`,`
 border-top-left-radius: var(--n-tab-border-radius);
 border-bottom-left-radius: var(--n-tab-border-radius);
 `,[w(`active`,`
 border-right: 1px solid #0000;
 `)]),f(`tabs-tab-pad`,`
 border-right: 1px solid var(--n-tab-border-color);
 `),f(`tabs-pad`,`
 border-right: 1px solid var(--n-tab-border-color);
 `)])]),w(`right`,[w(`card-type`,[f(`tabs-scroll-padding`,`border-left: 1px solid var(--n-tab-border-color);`),u(`prefix, suffix`,`
 border-left: 1px solid var(--n-tab-border-color);
 `),f(`tabs-tab`,`
 border-top-right-radius: var(--n-tab-border-radius);
 border-bottom-right-radius: var(--n-tab-border-radius);
 `,[w(`active`,`
 border-left: 1px solid #0000;
 `)]),f(`tabs-tab-pad`,`
 border-left: 1px solid var(--n-tab-border-color);
 `),f(`tabs-pad`,`
 border-left: 1px solid var(--n-tab-border-color);
 `)])]),w(`bottom`,[w(`card-type`,[f(`tabs-scroll-padding`,`border-top: 1px solid var(--n-tab-border-color);`),u(`prefix, suffix`,`
 border-top: 1px solid var(--n-tab-border-color);
 `),f(`tabs-tab`,`
 border-bottom-left-radius: var(--n-tab-border-radius);
 border-bottom-right-radius: var(--n-tab-border-radius);
 `,[w(`active`,`
 border-top: 1px solid #0000;
 `)]),f(`tabs-tab-pad`,`
 border-top: 1px solid var(--n-tab-border-color);
 `),f(`tabs-pad`,`
 border-top: 1px solid var(--n-tab-border-color);
 `)])])])]),Ke=ze,qe=y({name:`Tabs`,props:Object.assign(Object.assign({},m.props),{value:[String,Number],defaultValue:[String,Number],trigger:{type:String,default:`click`},type:{type:String,default:`bar`},closable:Boolean,justifyContent:String,size:String,placement:{type:String,default:`top`},tabStyle:[String,Object],tabClass:String,addTabStyle:[String,Object],addTabClass:String,barWidth:Number,paneClass:String,paneStyle:[String,Object],paneWrapperClass:String,paneWrapperStyle:[String,Object],addable:[Boolean,Object],tabsPadding:{type:Number,default:0},animated:Boolean,onBeforeLeave:Function,onAdd:Function,"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array],onClose:[Function,Array],labelSize:String,activeName:[String,Number],onActiveNameChange:[Function,Array]}),slots:Object,setup(e,{slots:t}){let{mergedClsPrefixRef:r,inlineThemeDisabled:i,mergedComponentPropsRef:a}=se(e),o=m(`Tabs`,`-tabs`,Ge,_e,e,r),s=H(null),c=H(null),l=H(null),u=H(null),d=H(null),f=H(null),h=H(!0),_=H(!0),v=pe(e,[`labelSize`,`size`]),y=F(()=>v.value?v.value:a?.value?.Tabs?.size||`medium`),b=pe(e,[`activeName`,`value`]),x=H(b.value??e.defaultValue??(t.default?A(t.default())[0]?.props?.name:null)),C=fe(b,x),w={id:0},E=F(()=>{if(!(!e.justifyContent||e.type===`card`))return{display:`flex`,justifyContent:e.justifyContent}});S(C,()=>{w.id=0,N(),ne()});function D(){let{value:e}=C;return e===null?null:s.value?.querySelector(`[data-name="${e}"]`)}function k(t){if(e.type===`card`)return;let{value:n}=c;if(!n)return;let i=n.style.opacity===`0`;if(t){let a=`${r.value}-tabs-bar--disabled`,{barWidth:o,placement:s}=e;if(t.dataset.disabled===`true`?n.classList.add(a):n.classList.remove(a),[`top`,`bottom`].includes(s)){if(M([`top`,`maxHeight`,`height`]),typeof o==`number`&&t.offsetWidth>=o){let e=Math.floor((t.offsetWidth-o)/2)+t.offsetLeft;n.style.left=`${e}px`,n.style.maxWidth=`${o}px`}else n.style.left=`${t.offsetLeft}px`,n.style.maxWidth=`${t.offsetWidth}px`;n.style.width=`8192px`,i&&(n.style.transition=`none`),n.offsetWidth,i&&(n.style.transition=``,n.style.opacity=`1`)}else{if(M([`left`,`maxWidth`,`width`]),typeof o==`number`&&t.offsetHeight>=o){let e=Math.floor((t.offsetHeight-o)/2)+t.offsetTop;n.style.top=`${e}px`,n.style.maxHeight=`${o}px`}else n.style.top=`${t.offsetTop}px`,n.style.maxHeight=`${t.offsetHeight}px`;n.style.height=`8192px`,i&&(n.style.transition=`none`),n.offsetHeight,i&&(n.style.transition=``,n.style.opacity=`1`)}}}function j(){if(e.type===`card`)return;let{value:t}=c;t&&(t.style.opacity=`0`)}function M(e){let{value:t}=c;if(t)for(let n of e)t.style[n]=``}function N(){if(e.type===`card`)return;let t=D();t?k(t):j()}function ne(){let e=d.value?.$el;if(!e)return;let t=D();if(!t)return;let{scrollLeft:n,offsetWidth:r}=e,{offsetLeft:i,offsetWidth:a}=t;n>i?e.scrollTo({top:0,left:i,behavior:`smooth`}):i+a>n+r&&e.scrollTo({top:0,left:i+a-r,behavior:`smooth`})}let I=H(null),L=0,R=null;function re(e){let t=I.value;if(t){L=e.getBoundingClientRect().height;let n=`${L}px`,r=()=>{t.style.height=n,t.style.maxHeight=n};R?(r(),R(),R=null):R=r}}function ie(e){let t=I.value;if(t){let n=e.getBoundingClientRect().height,r=()=>{document.body.offsetHeight,t.style.maxHeight=`${n}px`,t.style.height=`${Math.max(L,n)}px`};R?(R(),R=null,r()):R=r}}function ae(){let t=I.value;if(t){t.style.maxHeight=``,t.style.height=``;let{paneWrapperStyle:n}=e;if(typeof n==`string`)t.style.cssText=n;else if(n){let{maxHeight:e,height:r}=n;e!==void 0&&(t.style.maxHeight=e),r!==void 0&&(t.style.height=r)}}}let z={value:[]},B=H(`next`);function V(e){let t=C.value,n=`next`;for(let r of z.value){if(r===t)break;if(r===e){n=`prev`;break}}B.value=n,oe(e)}function oe(t){let{onActiveNameChange:n,onUpdateValue:r,"onUpdate:value":i}=e;n&&q(n,t),r&&q(r,t),i&&q(i,t),x.value=t}function U(t){let{onClose:n}=e;n&&q(n,t)}let W=!0;function G(){let{value:e}=c;if(!e)return;W||=!1;let t=`transition-disabled`;e.classList.add(t),N(),e.classList.remove(t)}let K=H(null);function J({transitionDisabled:e}){let t=s.value;if(!t)return;e&&t.classList.add(`transition-disabled`);let n=D();n&&K.value&&(K.value.style.width=`${n.offsetWidth}px`,K.value.style.height=`${n.offsetHeight}px`,K.value.style.transform=`translateX(${n.offsetLeft-ce(getComputedStyle(t).paddingLeft)}px)`,e&&K.value.offsetWidth),e&&t.classList.remove(`transition-disabled`)}S([C],()=>{e.type===`segment`&&P(()=>{J({transitionDisabled:!1})})}),g(()=>{e.type===`segment`&&J({transitionDisabled:!0})});let Y=0;function ue(t){if(t.contentRect.width===0&&t.contentRect.height===0||Y===t.contentRect.width)return;Y=t.contentRect.width;let{type:n}=e;if((n===`line`||n===`bar`)&&(W||e.justifyContent?.startsWith(`space`))&&G(),n!==`segment`){let{placement:t}=e;Z((t===`top`||t===`bottom`?d.value?.$el:f.value)||null)}}let de=Ke(ue,64);S([()=>e.justifyContent,()=>e.size],()=>{P(()=>{let{type:t}=e;(t===`line`||t===`bar`)&&G()})});let X=H(!1);function me(t){let{target:n,contentRect:{width:r,height:i}}=t,a=n.parentElement.parentElement.offsetWidth,o=n.parentElement.parentElement.offsetHeight,{placement:s}=e;if(!X.value)s===`top`||s===`bottom`?a<r&&(X.value=!0):o<i&&(X.value=!0);else{let{value:e}=u;if(!e)return;s===`top`||s===`bottom`?a-r>e.$el.offsetWidth&&(X.value=!1):o-i>e.$el.offsetHeight&&(X.value=!1)}Z(d.value?.$el||null)}let he=Ke(me,64);function ge(){let{onAdd:t}=e;t&&t(),P(()=>{let e=D(),{value:t}=d;!e||!t||t.scrollTo({left:e.offsetLeft,top:0,behavior:`smooth`})})}function Z(t){if(!t)return;let{placement:n}=e;if(n===`top`||n===`bottom`){let{scrollLeft:e,scrollWidth:n,offsetWidth:r}=t;h.value=e<=0,_.value=e+r>=n}else{let{scrollTop:e,scrollHeight:n,offsetHeight:r}=t;h.value=e<=0,_.value=e+r>=n}}let Q=Ke(e=>{Z(e.target)},64);p(Ve,{triggerRef:O(e,`trigger`),tabStyleRef:O(e,`tabStyle`),tabClassRef:O(e,`tabClass`),addTabStyleRef:O(e,`addTabStyle`),addTabClassRef:O(e,`addTabClass`),paneClassRef:O(e,`paneClass`),paneStyleRef:O(e,`paneStyle`),mergedClsPrefixRef:r,typeRef:O(e,`type`),closableRef:O(e,`closable`),valueRef:C,tabChangeIdRef:w,onBeforeLeaveRef:O(e,`onBeforeLeave`),activateTab:V,handleClose:U,handleAdd:ge}),le(()=>{N(),ne()}),ee(()=>{let{value:e}=l;if(!e)return;let{value:t}=r,n=`${t}-tabs-nav-scroll-wrapper--shadow-start`,i=`${t}-tabs-nav-scroll-wrapper--shadow-end`;h.value?e.classList.remove(n):e.classList.add(n),_.value?e.classList.remove(i):e.classList.add(i)});let ve={syncBarPosition:()=>{N()}},ye=()=>{J({transitionDisabled:!0})},$=F(()=>{let{value:t}=y,{type:r}=e,i=`${t}${{card:`Card`,bar:`Bar`,line:`Line`,segment:`Segment`}[r]}`,{self:{barColor:a,closeIconColor:s,closeIconColorHover:c,closeIconColorPressed:l,tabColor:u,tabBorderColor:d,paneTextColor:f,tabFontWeight:p,tabBorderRadius:m,tabFontWeightActive:h,colorSegment:g,fontWeightStrong:_,tabColorSegment:v,closeSize:b,closeIconSize:x,closeColorHover:S,closeColorPressed:ee,closeBorderRadius:C,[T(`panePadding`,t)]:w,[T(`tabPadding`,i)]:E,[T(`tabPaddingVertical`,i)]:D,[T(`tabGap`,i)]:O,[T(`tabGap`,`${i}Vertical`)]:k,[T(`tabTextColor`,r)]:A,[T(`tabTextColorActive`,r)]:j,[T(`tabTextColorHover`,r)]:M,[T(`tabTextColorDisabled`,r)]:N,[T(`tabFontSize`,t)]:P},common:{cubicBezierEaseInOut:te}}=o.value;return{"--n-bezier":te,"--n-color-segment":g,"--n-bar-color":a,"--n-tab-font-size":P,"--n-tab-text-color":A,"--n-tab-text-color-active":j,"--n-tab-text-color-disabled":N,"--n-tab-text-color-hover":M,"--n-pane-text-color":f,"--n-tab-border-color":d,"--n-tab-border-radius":m,"--n-close-size":b,"--n-close-icon-size":x,"--n-close-color-hover":S,"--n-close-color-pressed":ee,"--n-close-border-radius":C,"--n-close-icon-color":s,"--n-close-icon-color-hover":c,"--n-close-icon-color-pressed":l,"--n-tab-color":u,"--n-tab-font-weight":p,"--n-tab-font-weight-active":h,"--n-tab-padding":E,"--n-tab-padding-vertical":D,"--n-tab-gap":O,"--n-tab-gap-vertical":k,"--n-pane-padding-left":n(w,`left`),"--n-pane-padding-right":n(w,`right`),"--n-pane-padding-top":n(w,`top`),"--n-pane-padding-bottom":n(w,`bottom`),"--n-font-weight-strong":_,"--n-tab-color-segment":v}}),be=i?te(`tabs`,F(()=>`${y.value[0]}${e.type[0]}`),$,e):void 0;return Object.assign({mergedClsPrefix:r,mergedValue:C,renderedNames:new Set,segmentCapsuleElRef:K,tabsPaneWrapperRef:I,tabsElRef:s,barElRef:c,addTabInstRef:u,xScrollInstRef:d,scrollWrapperElRef:l,addTabFixed:X,tabWrapperStyle:E,handleNavResize:de,mergedSize:y,handleScroll:Q,handleTabsResize:he,cssVars:i?void 0:$,themeClass:be?.themeClass,animationDirection:B,renderNameListRef:z,yScrollElRef:f,handleSegmentResize:ye,onAnimationBeforeLeave:re,onAnimationEnter:ie,onAnimationAfterEnter:ae,onRender:be?.onRender},ve)},render(){let{mergedClsPrefix:e,type:t,placement:n,addTabFixed:r,addable:i,mergedSize:a,renderNameListRef:o,onRender:s,paneWrapperClass:c,paneWrapperStyle:l,$slots:{default:u,prefix:d,suffix:f}}=this;s?.();let p=u?A(u()).filter(e=>e.type.__TAB_PANE__===!0):[],m=u?A(u()).filter(e=>e.type.__TAB__===!0):[],h=!m.length,g=t===`card`,_=t===`segment`,v=!g&&!_&&this.justifyContent;o.value=[];let y=()=>{let t=G(`div`,{style:this.tabWrapperStyle,class:`${e}-tabs-wrapper`},v?null:G(`div`,{class:`${e}-tabs-scroll-padding`,style:n===`top`||n===`bottom`?{width:`${this.tabsPadding}px`}:{height:`${this.tabsPadding}px`}}),h?p.map((e,t)=>(o.value.push(e.props.name),Ze(G(We,Object.assign({},e.props,{internalCreatedByPane:!0,internalLeftPadded:t!==0&&(!v||v===`center`||v===`start`||v===`end`)}),e.children?{default:e.children.tab}:void 0)))):m.map((e,t)=>(o.value.push(e.props.name),Ze(t!==0&&!v?Xe(e):e))),!r&&i&&g?Ye(i,(h?p.length:m.length)!==0):null,v?null:G(`div`,{class:`${e}-tabs-scroll-padding`,style:{width:`${this.tabsPadding}px`}}));return G(`div`,{ref:`tabsElRef`,class:`${e}-tabs-nav-scroll-content`},g&&i?G(x,{onResize:this.handleTabsResize},{default:()=>t}):t,g?G(`div`,{class:`${e}-tabs-pad`}):null,g?null:G(`div`,{ref:`barElRef`,class:`${e}-tabs-bar`}))},b=_?`top`:n;return G(`div`,{class:[`${e}-tabs`,this.themeClass,`${e}-tabs--${t}-type`,`${e}-tabs--${a}-size`,v&&`${e}-tabs--flex`,`${e}-tabs--${b}`],style:this.cssVars},G(`div`,{class:[`${e}-tabs-nav--${t}-type`,`${e}-tabs-nav--${b}`,`${e}-tabs-nav`]},D(d,t=>t&&G(`div`,{class:`${e}-tabs-nav__prefix`},t)),_?G(x,{onResize:this.handleSegmentResize},{default:()=>G(`div`,{class:`${e}-tabs-rail`,ref:`tabsElRef`},G(`div`,{class:`${e}-tabs-capsule`,ref:`segmentCapsuleElRef`},G(`div`,{class:`${e}-tabs-wrapper`},G(`div`,{class:`${e}-tabs-tab`}))),h?p.map((e,t)=>(o.value.push(e.props.name),G(We,Object.assign({},e.props,{internalCreatedByPane:!0,internalLeftPadded:t!==0}),e.children?{default:e.children.tab}:void 0))):m.map((e,t)=>(o.value.push(e.props.name),t===0?e:Xe(e))))}):G(x,{onResize:this.handleNavResize},{default:()=>G(`div`,{class:`${e}-tabs-nav-scroll-wrapper`,ref:`scrollWrapperElRef`},[`top`,`bottom`].includes(b)?G(Se,{ref:`xScrollInstRef`,onScroll:this.handleScroll},{default:y}):G(`div`,{class:`${e}-tabs-nav-y-scroll`,onScroll:this.handleScroll,ref:`yScrollElRef`},y()))}),r&&i&&g?Ye(i,!0):null,D(f,t=>t&&G(`div`,{class:`${e}-tabs-nav__suffix`},t))),h&&(this.animated&&(b===`top`||b===`bottom`)?G(`div`,{ref:`tabsPaneWrapperRef`,style:l,class:[`${e}-tabs-pane-wrapper`,c]},Je(p,this.mergedValue,this.renderedNames,this.onAnimationBeforeLeave,this.onAnimationEnter,this.onAnimationAfterEnter,this.animationDirection)):Je(p,this.mergedValue,this.renderedNames)))}});function Je(e,t,n,r,i,a,o){let s=[];return e.forEach(e=>{let{name:r,displayDirective:i,"display-directive":a}=e.props,o=e=>i===e||a===e,c=t===r;if(e.key!==void 0&&(e.key=r),c||o(`show`)||o(`show:lazy`)&&n.has(r)){n.has(r)||n.add(r);let t=!o(`if`);s.push(t?d(e,[[I,c]]):e)}}),o?G(ie,{name:`${o}-transition`,onBeforeLeave:r,onEnter:i,onAfterEnter:a},{default:()=>s}):s}function Ye(e,t){return G(We,{ref:`addTabInstRef`,key:`__addable`,name:`__addable`,internalCreatedByPane:!0,internalAddable:!0,internalLeftPadded:t,disabled:typeof e==`object`&&e.disabled})}function Xe(e){let t=R(e);return t.props?t.props.internalLeftPadded=!0:t.props={internalLeftPadded:!0},t}function Ze(e){return Array.isArray(e.dynamicProps)?e.dynamicProps.includes(`internalLeftPadded`)||e.dynamicProps.push(`internalLeftPadded`):e.dynamicProps=[`internalLeftPadded`],e}var Qe={key:0,style:{padding:`40px`,"text-align":`center`}},$e={style:{"min-width":`0`,flex:`1`}},et=y({__name:`LiveTail`,props:{events:{},connected:{type:Boolean},paused:{type:Boolean}},emits:[`pause`,`resume`,`clear`],setup(e,{emit:t}){let n=e,r=t,i=H(null),a=H(!0);function o(e){return e===`postgres_changes`?`info`:e===`broadcast`?`success`:e===`presence`?`warning`:e===`error`?`error`:`default`}function c(e){return e.toLocaleTimeString(`en-US`,{hour12:!1,fractionalSecondDigits:3})}S(()=>n.events.length,async()=>{if(!a.value)return;await P();let e=i.value;e&&(e.scrollTop=e.scrollHeight)});function u(){let e=i.value;e&&(a.value=e.scrollHeight-e.scrollTop-e.clientHeight<40)}return(t,n)=>(l(),W(`div`,null,[K(B(V),{align:`center`,size:8,style:{"margin-bottom":`8px`}},{default:s(()=>[K(B(X),{type:e.connected?`success`:`default`,size:`small`,bordered:!1},{default:s(()=>[k(U(e.connected?`Connected`:`Disconnected`),1)]),_:1},8,[`type`]),e.paused?(l(),M(B(X),{key:0,type:`warning`,size:`small`,bordered:!1},{default:s(()=>[...n[3]||=[k(` Paused `,-1)]]),_:1})):E(``,!0),K(B(Q),{depth:`3`,style:{"font-size":`12px`}},{default:s(()=>[k(U(e.events.length.toLocaleString())+` events `,1)]),_:1}),e.paused?(l(),M(B(j),{key:2,size:`tiny`,type:`info`,onClick:n[1]||=e=>r(`resume`)},{default:s(()=>[...n[5]||=[k(`Resume`,-1)]]),_:1})):(l(),M(B(j),{key:1,size:`tiny`,onClick:n[0]||=e=>r(`pause`)},{default:s(()=>[...n[4]||=[k(`Pause`,-1)]]),_:1})),K(B(j),{size:`tiny`,onClick:n[2]||=e=>r(`clear`)},{default:s(()=>[...n[6]||=[k(`Clear`,-1)]]),_:1})]),_:1}),N(`div`,{ref_key:`listEl`,ref:i,style:{height:`calc(100vh - 380px)`,"min-height":`200px`,"overflow-y":`auto`,border:`1px solid rgba(255, 255, 255, 0.08)`,"border-radius":`4px`,background:`rgba(0, 0, 0, 0.15)`},onScroll:u},[e.events.length===0?(l(),W(`div`,Qe,[K(B(Q),{depth:`3`,style:{"font-size":`13px`}},{default:s(()=>[...n[7]||=[k(` Waiting for events… `,-1)]]),_:1})])):E(``,!0),(l(!0),W(oe,null,_(e.events,(e,t)=>(l(),W(`div`,{key:t,style:{display:`flex`,"align-items":`flex-start`,gap:`10px`,padding:`6px 12px`,"border-bottom":`1px solid rgba(255, 255, 255, 0.04)`,"font-family":`monospace`,"font-size":`12px`}},[K(B(Q),{depth:`3`,style:{"white-space":`nowrap`,"flex-shrink":`0`,"min-width":`88px`}},{default:s(()=>[k(U(c(e.receivedAt)),1)]),_:2},1024),K(B(X),{type:o(e.event),size:`tiny`,style:{"flex-shrink":`0`}},{default:s(()=>[k(U(e.event),1)]),_:2},1032,[`type`]),N(`div`,$e,[K(be,{value:e.payload},null,8,[`value`])])]))),128))],544)]))}});function tt(e,t,n){let r=ae([]),i=H(!1),a=H(!1),s=new EventSource(`/admin/api/v1${e}`,{withCredentials:!0});s.onopen=()=>{i.value=!0},s.onerror=()=>{i.value=!1};let c=(e,n)=>{a.value||(r.value=[...r.value,t(e,n)],r.value.length>1e3&&(r.value=r.value.slice(-1e3)))};if(n&&n.length>0)for(let e of n)s.addEventListener(e,t=>{c(e,t.data)});else s.onmessage=e=>{c(`message`,e.data)};let l=()=>{a.value=!0},u=()=>{a.value=!1},d=()=>{r.value=[]},f=!1,p=()=>{f||(f=!0,i.value=!1,s.close())};return o(()=>p()),{events:r,connected:i,paused:a,pause:l,resume:u,clear:d,close:p}}var nt=y({__name:`Tables`,setup(e){let{data:t,loading:n,error:r,refresh:i}=ve(()=>ge.tables()),a=[{title:`Schema`,key:`schema_name`,width:140},{title:`Table`,key:`table_name`,width:200},{title:`Primary Key`,key:`pk_columns`,width:180,render:e=>e.pk_columns.length?G(X,{size:`small`,type:`info`,bordered:!1},{default:()=>e.pk_columns.join(`, `)}):G(Q,{depth:3},{default:()=>`—`})},{title:`Owner Column`,key:`owner_column`,width:140,render:e=>e.owner_column??G(Q,{depth:3},{default:()=>`—`})},{title:`Enabled At`,key:`created_at`,width:170,render:e=>new Date(e.created_at).toLocaleString()}];return(e,o)=>(l(),M(B(re),{title:`Enabled Tables`,size:`small`},{default:s(()=>[K(ye,{error:B(r),retry:B(i)},null,8,[`error`,`retry`]),K(B(he),{show:B(n)},{default:s(()=>[B(t)&&B(t).length>0?(l(),M(B(me),{key:0,columns:a,data:B(t),bordered:!1,size:`small`},null,8,[`data`])):B(t)&&B(t).length===0?(l(),M($,{key:1,description:`No tables are realtime-enabled. Enable tables via SQL migrations.`})):E(``,!0)]),_:1},8,[`show`])]),_:1}))}}),rt=y({__name:`Channels`,setup(e){let t=H(`inspector`),n=H(`realtime:public`),r=H(null),i=ae(null);function a(e,t){let n=JSON.parse(t);return{event:e,topic:n.topic??``,payload:n.payload??{raw:t},receivedAt:new Date}}let o=[`postgres_changes`,`broadcast`,`presence`,`presence_diff`,`presence_state`,`connected`,`heartbeat`,`error`];function c(){let e=n.value.trim();e&&(u(),r.value=e,i.value=tt(`/realtime/inspect?topic=${encodeURIComponent(e)}`,a,o))}function u(){i.value&&i.value.close(),i.value=null,r.value=null}return(e,r)=>(l(),W(`div`,null,[r[7]||=N(`div`,{style:{display:`flex`,"align-items":`center`,"justify-content":`space-between`,"margin-bottom":`16px`}},[N(`h1`,{style:{margin:`0`,"font-size":`20px`,"font-weight":`600`}},` Realtime `)],-1),K(B(qe),{value:t.value,"onUpdate:value":r[4]||=e=>t.value=e,type:`line`,animated:``},{default:s(()=>[K(B(Ue),{name:`inspector`,tab:`Inspector`},{default:s(()=>[K(B(re),{size:`small`},{default:s(()=>[K(B(V),{vertical:``,size:16},{default:s(()=>[K(B(V),{align:`center`,size:8},{default:s(()=>[K(B(de),{value:n.value,"onUpdate:value":r[0]||=e=>n.value=e,placeholder:`e.g. realtime:room-42`,style:{width:`340px`},disabled:!!i.value,onKeyup:z(c,[`enter`])},null,8,[`value`,`disabled`]),i.value?(l(),M(B(j),{key:1,size:`small`,onClick:u},{default:s(()=>[...r[6]||=[k(` Disconnect `,-1)]]),_:1})):(l(),M(B(j),{key:0,type:`primary`,size:`small`,onClick:c},{default:s(()=>[...r[5]||=[k(` Connect `,-1)]]),_:1}))]),_:1}),i.value?(l(),M(et,{key:0,events:i.value.events.value,connected:i.value.connected.value,paused:i.value.paused.value,onPause:r[1]||=e=>i.value.pause(),onResume:r[2]||=e=>i.value.resume(),onClear:r[3]||=e=>i.value.clear()},null,8,[`events`,`connected`,`paused`])):(l(),M($,{key:1,description:`Subscribe to a topic to begin tailing.`}))]),_:1})]),_:1})]),_:1}),K(B(Ue),{name:`tables`,tab:`Enabled Tables`},{default:s(()=>[K(nt)]),_:1})]),_:1},8,[`value`])]))}});export{rt as default};
//# sourceMappingURL=Channels-BoIuTtam.js.map