import{A as e,En as t,Gt as n,Jt as r,Kn as i,Kt as a,Ln as o,Mn as s,O as c,On as l,S as u,Sn as d,St as f,Un as p,Wn as m,Yt as h,ar as g,j as _,jt as v,lt as y,mn as b,nn as x,on as S,p as C,tr as w,ut as T,v as E,wn as D,xt as O}from"./Space-n5-XcguU.js";import{B as k,I as A,L as j,M,O as N,S as P,V as F,j as I,w as L}from"./Select-DIzZyRZb.js";import{t as R}from"./use-merged-state-BvhkaHNX.js";import{t as z}from"./format-length-CGCY1rMh.js";import{B,V,v as H}from"./index-CeE6v959.js";var U=d({name:`NDrawerContent`,inheritAttrs:!1,props:{blockScroll:Boolean,show:{type:Boolean,default:void 0},displayDirective:{type:String,required:!0},placement:{type:String,required:!0},contentClass:String,contentStyle:[Object,String],nativeScrollbar:{type:Boolean,required:!0},scrollbarProps:Object,trapFocus:{type:Boolean,default:!0},autoFocus:{type:Boolean,default:!0},showMask:{type:[Boolean,String],required:!0},maxWidth:Number,maxHeight:Number,minWidth:Number,minHeight:Number,resizable:Boolean,onClickoutside:Function,onAfterLeave:Function,onAfterEnter:Function,onEsc:Function},setup(e){let n=w(!!e.show),r=w(null),i=t(F),a=0,c=``,l=null,u=w(!1),d=w(!1),f=b(()=>e.placement===`top`||e.placement===`bottom`),{mergedClsPrefixRef:h,mergedRtlRef:g}=T(e),v=_(`Drawer`,g,h),y=L,x=e=>{d.value=!0,a=f.value?e.clientY:e.clientX,c=document.body.style.cursor,document.body.style.cursor=f.value?`ns-resize`:`ew-resize`,document.body.addEventListener(`mousemove`,I),document.body.addEventListener(`mouseleave`,y),document.body.addEventListener(`mouseup`,L)},C=()=>{l!==null&&(window.clearTimeout(l),l=null),d.value?u.value=!0:l=window.setTimeout(()=>{u.value=!0},300)},E=()=>{l!==null&&(window.clearTimeout(l),l=null),u.value=!1},{doUpdateHeight:D,doUpdateWidth:O}=i,N=t=>{let{maxWidth:n}=e;if(n&&t>n)return n;let{minWidth:r}=e;return r&&t<r?r:t},P=t=>{let{maxHeight:n}=e;if(n&&t>n)return n;let{minHeight:r}=e;return r&&t<r?r:t};function I(t){if(d.value)if(f.value){let n=r.value?.offsetHeight||0,i=a-t.clientY;n+=e.placement===`bottom`?i:-i,n=P(n),D(n),a=t.clientY}else{let n=r.value?.offsetWidth||0,i=a-t.clientX;n+=e.placement===`right`?i:-i,n=N(n),O(n),a=t.clientX}}function L(){d.value&&(a=0,d.value=!1,document.body.style.cursor=c,document.body.removeEventListener(`mousemove`,I),document.body.removeEventListener(`mouseup`,L),document.body.removeEventListener(`mouseleave`,y))}m(()=>{e.show&&(n.value=!0)}),p(()=>e.show,e=>{e||L()}),s(()=>{L()});let R=b(()=>{let{show:t}=e,n=[[S,t]];return e.showMask||n.push([M,e.onClickoutside,void 0,{capture:!0}]),n});function z(){var t;n.value=!1,(t=e.onAfterLeave)==null||t.call(e)}return B(b(()=>e.blockScroll&&n.value)),o(k,r),o(A,null),o(j,null),{bodyRef:r,rtlEnabled:v,mergedClsPrefix:i.mergedClsPrefixRef,isMounted:i.isMountedRef,mergedTheme:i.mergedThemeRef,displayed:n,transitionName:b(()=>({right:`slide-in-from-right-transition`,left:`slide-in-from-left-transition`,top:`slide-in-from-top-transition`,bottom:`slide-in-from-bottom-transition`})[e.placement]),handleAfterLeave:z,bodyDirectives:R,handleMousedownResizeTrigger:x,handleMouseenterResizeTrigger:C,handleMouseleaveResizeTrigger:E,isDragging:d,isHoverOnResizeTrigger:u}},render(){let{$slots:e,mergedClsPrefix:t}=this;return this.displayDirective===`show`||this.displayed||this.show?i(D(`div`,{role:`none`},D(L,{disabled:!this.showMask||!this.trapFocus,active:this.show,autoFocus:this.autoFocus,onEsc:this.onEsc},{default:()=>D(x,{name:this.transitionName,appear:this.isMounted,onAfterEnter:this.onAfterEnter,onAfterLeave:this.handleAfterLeave},{default:()=>i(D(`div`,l(this.$attrs,{role:`dialog`,ref:`bodyRef`,"aria-modal":`true`,class:[`${t}-drawer`,this.rtlEnabled&&`${t}-drawer--rtl`,`${t}-drawer--${this.placement}-placement`,this.isDragging&&`${t}-drawer--unselectable`,this.nativeScrollbar&&`${t}-drawer--native-scrollbar`]}),[this.resizable?D(`div`,{class:[`${t}-drawer__resize-trigger`,(this.isDragging||this.isHoverOnResizeTrigger)&&`${t}-drawer__resize-trigger--hover`],onMouseenter:this.handleMouseenterResizeTrigger,onMouseleave:this.handleMouseleaveResizeTrigger,onMousedown:this.handleMousedownResizeTrigger}):null,this.nativeScrollbar?D(`div`,{class:[`${t}-drawer-content-wrapper`,this.contentClass],style:this.contentStyle,role:`none`},e):D(C,Object.assign({},this.scrollbarProps,{contentStyle:this.contentStyle,contentClass:[`${t}-drawer-content-wrapper`,this.contentClass],theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar}),e)]),this.bodyDirectives)})})),[[S,this.displayDirective===`if`||this.displayed||this.show]]):null}}),{cubicBezierEaseIn:W,cubicBezierEaseOut:G}=e;function K({duration:e=`0.3s`,leaveDuration:t=`0.2s`,name:r=`slide-in-from-bottom`}={}){return[n(`&.${r}-transition-leave-active`,{transition:`transform ${t} ${W}`}),n(`&.${r}-transition-enter-active`,{transition:`transform ${e} ${G}`}),n(`&.${r}-transition-enter-to`,{transform:`translateY(0)`}),n(`&.${r}-transition-enter-from`,{transform:`translateY(100%)`}),n(`&.${r}-transition-leave-from`,{transform:`translateY(0)`}),n(`&.${r}-transition-leave-to`,{transform:`translateY(100%)`})]}var{cubicBezierEaseIn:q,cubicBezierEaseOut:J}=e;function Y({duration:e=`0.3s`,leaveDuration:t=`0.2s`,name:r=`slide-in-from-left`}={}){return[n(`&.${r}-transition-leave-active`,{transition:`transform ${t} ${q}`}),n(`&.${r}-transition-enter-active`,{transition:`transform ${e} ${J}`}),n(`&.${r}-transition-enter-to`,{transform:`translateX(0)`}),n(`&.${r}-transition-enter-from`,{transform:`translateX(-100%)`}),n(`&.${r}-transition-leave-from`,{transform:`translateX(0)`}),n(`&.${r}-transition-leave-to`,{transform:`translateX(-100%)`})]}var{cubicBezierEaseIn:X,cubicBezierEaseOut:Z}=e;function Q({duration:e=`0.3s`,leaveDuration:t=`0.2s`,name:r=`slide-in-from-right`}={}){return[n(`&.${r}-transition-leave-active`,{transition:`transform ${t} ${X}`}),n(`&.${r}-transition-enter-active`,{transition:`transform ${e} ${Z}`}),n(`&.${r}-transition-enter-to`,{transform:`translateX(0)`}),n(`&.${r}-transition-enter-from`,{transform:`translateX(100%)`}),n(`&.${r}-transition-leave-from`,{transform:`translateX(0)`}),n(`&.${r}-transition-leave-to`,{transform:`translateX(100%)`})]}var{cubicBezierEaseIn:$,cubicBezierEaseOut:ee}=e;function te({duration:e=`0.3s`,leaveDuration:t=`0.2s`,name:r=`slide-in-from-top`}={}){return[n(`&.${r}-transition-leave-active`,{transition:`transform ${t} ${$}`}),n(`&.${r}-transition-enter-active`,{transition:`transform ${e} ${ee}`}),n(`&.${r}-transition-enter-to`,{transform:`translateY(0)`}),n(`&.${r}-transition-enter-from`,{transform:`translateY(-100%)`}),n(`&.${r}-transition-leave-from`,{transform:`translateY(0)`}),n(`&.${r}-transition-leave-to`,{transform:`translateY(-100%)`})]}var ne=n([a(`drawer`,`
 word-break: break-word;
 line-height: var(--n-line-height);
 position: absolute;
 pointer-events: all;
 box-shadow: var(--n-box-shadow);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 background-color: var(--n-color);
 color: var(--n-text-color);
 box-sizing: border-box;
 `,[Q(),Y(),te(),K(),h(`unselectable`,`
 user-select: none; 
 -webkit-user-select: none;
 `),h(`native-scrollbar`,[a(`drawer-content-wrapper`,`
 overflow: auto;
 height: 100%;
 `)]),r(`resize-trigger`,`
 position: absolute;
 background-color: #0000;
 transition: background-color .3s var(--n-bezier);
 `,[h(`hover`,`
 background-color: var(--n-resize-trigger-color-hover);
 `)]),a(`drawer-content-wrapper`,`
 box-sizing: border-box;
 `),a(`drawer-content`,`
 height: 100%;
 display: flex;
 flex-direction: column;
 `,[h(`native-scrollbar`,[a(`drawer-body-content-wrapper`,`
 height: 100%;
 overflow: auto;
 `)]),a(`drawer-body`,`
 flex: 1 0 0;
 overflow: hidden;
 `),a(`drawer-body-content-wrapper`,`
 box-sizing: border-box;
 padding: var(--n-body-padding);
 `),a(`drawer-header`,`
 font-weight: var(--n-title-font-weight);
 line-height: 1;
 font-size: var(--n-title-font-size);
 color: var(--n-title-text-color);
 padding: var(--n-header-padding);
 transition: border .3s var(--n-bezier);
 border-bottom: 1px solid var(--n-divider-color);
 border-bottom: var(--n-header-border-bottom);
 display: flex;
 justify-content: space-between;
 align-items: center;
 `,[r(`main`,`
 flex: 1;
 `),r(`close`,`
 margin-left: 6px;
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `)]),a(`drawer-footer`,`
 display: flex;
 justify-content: flex-end;
 border-top: var(--n-footer-border-top);
 transition: border .3s var(--n-bezier);
 padding: var(--n-footer-padding);
 `)]),h(`right-placement`,`
 top: 0;
 bottom: 0;
 right: 0;
 border-top-left-radius: var(--n-border-radius);
 border-bottom-left-radius: var(--n-border-radius);
 `,[r(`resize-trigger`,`
 width: 3px;
 height: 100%;
 top: 0;
 left: 0;
 transform: translateX(-1.5px);
 cursor: ew-resize;
 `)]),h(`left-placement`,`
 top: 0;
 bottom: 0;
 left: 0;
 border-top-right-radius: var(--n-border-radius);
 border-bottom-right-radius: var(--n-border-radius);
 `,[r(`resize-trigger`,`
 width: 3px;
 height: 100%;
 top: 0;
 right: 0;
 transform: translateX(1.5px);
 cursor: ew-resize;
 `)]),h(`top-placement`,`
 top: 0;
 left: 0;
 right: 0;
 border-bottom-left-radius: var(--n-border-radius);
 border-bottom-right-radius: var(--n-border-radius);
 `,[r(`resize-trigger`,`
 width: 100%;
 height: 3px;
 bottom: 0;
 left: 0;
 transform: translateY(1.5px);
 cursor: ns-resize;
 `)]),h(`bottom-placement`,`
 left: 0;
 bottom: 0;
 right: 0;
 border-top-left-radius: var(--n-border-radius);
 border-top-right-radius: var(--n-border-radius);
 `,[r(`resize-trigger`,`
 width: 100%;
 height: 3px;
 top: 0;
 left: 0;
 transform: translateY(-1.5px);
 cursor: ns-resize;
 `)])]),n(`body`,[n(`>`,[a(`drawer-container`,`
 position: fixed;
 `)])]),a(`drawer-container`,`
 position: relative;
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 pointer-events: none;
 `,[n(`> *`,`
 pointer-events: all;
 `)]),a(`drawer-mask`,`
 background-color: rgba(0, 0, 0, .3);
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `,[h(`invisible`,`
 background-color: rgba(0, 0, 0, 0)
 `),E({enterDuration:`0.2s`,leaveDuration:`0.2s`,enterCubicBezier:`var(--n-bezier-in)`,leaveCubicBezier:`var(--n-bezier-out)`})])]),re=d({name:`Drawer`,inheritAttrs:!1,props:Object.assign(Object.assign({},c.props),{show:Boolean,width:[Number,String],height:[Number,String],placement:{type:String,default:`right`},maskClosable:{type:Boolean,default:!0},showMask:{type:[Boolean,String],default:!0},to:[String,Object],displayDirective:{type:String,default:`if`},nativeScrollbar:{type:Boolean,default:!0},zIndex:Number,onMaskClick:Function,scrollbarProps:Object,contentClass:String,contentStyle:[Object,String],trapFocus:{type:Boolean,default:!0},onEsc:Function,autoFocus:{type:Boolean,default:!0},closeOnEsc:{type:Boolean,default:!0},blockScroll:{type:Boolean,default:!0},maxWidth:Number,maxHeight:Number,minWidth:Number,minHeight:Number,resizable:Boolean,defaultWidth:{type:[Number,String],default:251},defaultHeight:{type:[Number,String],default:251},onUpdateWidth:[Function,Array],onUpdateHeight:[Function,Array],"onUpdate:width":[Function,Array],"onUpdate:height":[Function,Array],"onUpdate:show":[Function,Array],onUpdateShow:[Function,Array],onAfterEnter:Function,onAfterLeave:Function,drawerStyle:[String,Object],drawerClass:String,target:null,onShow:Function,onHide:Function}),setup(e){let{mergedClsPrefixRef:t,namespaceRef:n,inlineThemeDisabled:r}=T(e),i=v(),a=c(`Drawer`,`-drawer`,ne,H,e,t),s=w(e.defaultWidth),l=w(e.defaultHeight),u=R(g(e,`width`),s),d=R(g(e,`height`),l),f=b(()=>{let{placement:t}=e;return t===`top`||t===`bottom`?``:z(u.value)}),p=b(()=>{let{placement:t}=e;return t===`left`||t===`right`?``:z(d.value)}),m=t=>{let{onUpdateWidth:n,"onUpdate:width":r}=e;n&&O(n,t),r&&O(r,t),s.value=t},h=t=>{let{onUpdateHeight:n,"onUpdate:width":r}=e;n&&O(n,t),r&&O(r,t),l.value=t},_=b(()=>[{width:f.value,height:p.value},e.drawerStyle||``]);function x(t){let{onMaskClick:n,maskClosable:r}=e;r&&D(!1),n&&n(t)}function S(e){x(e)}let C=V();function E(t){var n;(n=e.onEsc)==null||n.call(e),e.show&&e.closeOnEsc&&P(t)&&(C.value||D(!1))}function D(t){let{onHide:n,onUpdateShow:r,"onUpdate:show":i}=e;r&&O(r,t),i&&O(i,t),n&&!t&&O(n,t)}o(F,{isMountedRef:i,mergedThemeRef:a,mergedClsPrefixRef:t,doUpdateShow:D,doUpdateHeight:h,doUpdateWidth:m});let k=b(()=>{let{common:{cubicBezierEaseInOut:e,cubicBezierEaseIn:t,cubicBezierEaseOut:n},self:{color:r,textColor:i,boxShadow:o,lineHeight:s,headerPadding:c,footerPadding:l,borderRadius:u,bodyPadding:d,titleFontSize:f,titleTextColor:p,titleFontWeight:m,headerBorderBottom:h,footerBorderTop:g,closeIconColor:_,closeIconColorHover:v,closeIconColorPressed:y,closeColorHover:b,closeColorPressed:x,closeIconSize:S,closeSize:C,closeBorderRadius:w,resizableTriggerColorHover:T}}=a.value;return{"--n-line-height":s,"--n-color":r,"--n-border-radius":u,"--n-text-color":i,"--n-box-shadow":o,"--n-bezier":e,"--n-bezier-out":n,"--n-bezier-in":t,"--n-header-padding":c,"--n-body-padding":d,"--n-footer-padding":l,"--n-title-text-color":p,"--n-title-font-size":f,"--n-title-font-weight":m,"--n-header-border-bottom":h,"--n-footer-border-top":g,"--n-close-icon-color":_,"--n-close-icon-color-hover":v,"--n-close-icon-color-pressed":y,"--n-close-size":C,"--n-close-color-hover":b,"--n-close-color-pressed":x,"--n-close-icon-size":S,"--n-close-border-radius":w,"--n-resize-trigger-color-hover":T}}),A=r?y(`drawer`,void 0,k,e):void 0;return{mergedClsPrefix:t,namespace:n,mergedBodyStyle:_,handleOutsideClick:S,handleMaskClick:x,handleEsc:E,mergedTheme:a,cssVars:r?void 0:k,themeClass:A?.themeClass,onRender:A?.onRender,isMounted:i}},render(){let{mergedClsPrefix:e}=this;return D(N,{to:this.to,show:this.show},{default:()=>{var t;return(t=this.onRender)==null||t.call(this),i(D(`div`,{class:[`${e}-drawer-container`,this.namespace,this.themeClass],style:this.cssVars,role:`none`},this.showMask?D(x,{name:`fade-in-transition`,appear:this.isMounted},{default:()=>this.show?D(`div`,{"aria-hidden":!0,class:[`${e}-drawer-mask`,this.showMask===`transparent`&&`${e}-drawer-mask--invisible`],onClick:this.handleMaskClick}):null}):null,D(U,Object.assign({},this.$attrs,{class:[this.drawerClass,this.$attrs.class],style:[this.mergedBodyStyle,this.$attrs.style],blockScroll:this.blockScroll,contentStyle:this.contentStyle,contentClass:this.contentClass,placement:this.placement,scrollbarProps:this.scrollbarProps,show:this.show,displayDirective:this.displayDirective,nativeScrollbar:this.nativeScrollbar,onAfterEnter:this.onAfterEnter,onAfterLeave:this.onAfterLeave,trapFocus:this.trapFocus,autoFocus:this.autoFocus,resizable:this.resizable,maxHeight:this.maxHeight,minHeight:this.minHeight,maxWidth:this.maxWidth,minWidth:this.minWidth,showMask:this.showMask,onEsc:this.handleEsc,onClickoutside:this.handleOutsideClick}),this.$slots)),[[I,{zIndex:this.zIndex,enabled:this.show}]])}})}}),ie=d({name:`DrawerContent`,props:{title:String,headerClass:String,headerStyle:[Object,String],footerClass:String,footerStyle:[Object,String],bodyClass:String,bodyStyle:[Object,String],bodyContentClass:String,bodyContentStyle:[Object,String],nativeScrollbar:{type:Boolean,default:!0},scrollbarProps:Object,closable:Boolean},slots:Object,setup(){let e=t(F,null);e||f(`drawer-content`,"`n-drawer-content` must be placed inside `n-drawer`.");let{doUpdateShow:n}=e;function r(){n(!1)}return{handleCloseClick:r,mergedTheme:e.mergedThemeRef,mergedClsPrefix:e.mergedClsPrefixRef}},render(){let{title:e,mergedClsPrefix:t,nativeScrollbar:n,mergedTheme:r,bodyClass:i,bodyStyle:a,bodyContentClass:o,bodyContentStyle:s,headerClass:c,headerStyle:l,footerClass:d,footerStyle:f,scrollbarProps:p,closable:m,$slots:h}=this;return D(`div`,{role:`none`,class:[`${t}-drawer-content`,n&&`${t}-drawer-content--native-scrollbar`]},h.header||e||m?D(`div`,{class:[`${t}-drawer-header`,c],style:l,role:`none`},D(`div`,{class:`${t}-drawer-header__main`,role:`heading`,"aria-level":`1`},h.header===void 0?e:h.header()),m&&D(u,{onClick:this.handleCloseClick,clsPrefix:t,class:`${t}-drawer-header__close`,absolute:!0})):null,n?D(`div`,{class:[`${t}-drawer-body`,i],style:a,role:`none`},D(`div`,{class:[`${t}-drawer-body-content-wrapper`,o],style:s,role:`none`},h)):D(C,Object.assign({themeOverrides:r.peerOverrides.Scrollbar,theme:r.peers.Scrollbar},p,{class:`${t}-drawer-body`,contentClass:[`${t}-drawer-body-content-wrapper`,o],contentStyle:s}),h),h.footer?D(`div`,{class:[`${t}-drawer-footer`,d],style:f,role:`none`},h.footer()):null)}});export{re as n,ie as t};
//# sourceMappingURL=DrawerContent-TpYTFgF1.js.map