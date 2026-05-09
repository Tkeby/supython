import{Bt as e,E as t,Ft as n,Gt as r,It as i,Jt as a,Kt as o,O as s,On as c,S as l,Sn as u,Yt as d,Zt as f,_ as p,_t as m,ht as h,j as g,lt as _,mn as v,tr as y,ut as b,wn as x,x as S}from"./Space-n5-XcguU.js";import{F as C,I as w,L as T,M as E,N as D,P as O}from"./index-CeE6v959.js";function k(e){let{lineHeight:t,borderRadius:r,fontWeightStrong:a,baseColor:o,dividerColor:s,actionColor:c,textColor1:l,textColor2:u,closeColorHover:d,closeColorPressed:f,closeIconColor:p,closeIconColorHover:m,closeIconColorPressed:h,infoColor:g,successColor:_,warningColor:v,errorColor:y,fontSize:b}=e;return Object.assign(Object.assign({},D),{fontSize:b,lineHeight:t,titleFontWeight:a,borderRadius:r,border:`1px solid ${s}`,color:c,titleTextColor:l,iconColor:u,contentTextColor:u,closeBorderRadius:r,closeColorHover:d,closeColorPressed:f,closeIconColor:p,closeIconColorHover:m,closeIconColorPressed:h,borderInfo:`1px solid ${i(o,n(g,{alpha:.25}))}`,colorInfo:i(o,n(g,{alpha:.08})),titleTextColorInfo:l,iconColorInfo:g,contentTextColorInfo:u,closeColorHoverInfo:d,closeColorPressedInfo:f,closeIconColorInfo:p,closeIconColorHoverInfo:m,closeIconColorPressedInfo:h,borderSuccess:`1px solid ${i(o,n(_,{alpha:.25}))}`,colorSuccess:i(o,n(_,{alpha:.08})),titleTextColorSuccess:l,iconColorSuccess:_,contentTextColorSuccess:u,closeColorHoverSuccess:d,closeColorPressedSuccess:f,closeIconColorSuccess:p,closeIconColorHoverSuccess:m,closeIconColorPressedSuccess:h,borderWarning:`1px solid ${i(o,n(v,{alpha:.33}))}`,colorWarning:i(o,n(v,{alpha:.08})),titleTextColorWarning:l,iconColorWarning:v,contentTextColorWarning:u,closeColorHoverWarning:d,closeColorPressedWarning:f,closeIconColorWarning:p,closeIconColorHoverWarning:m,closeIconColorPressedWarning:h,borderError:`1px solid ${i(o,n(y,{alpha:.25}))}`,colorError:i(o,n(y,{alpha:.08})),titleTextColorError:l,iconColorError:y,contentTextColorError:u,closeColorHoverError:d,closeColorPressedError:f,closeIconColorError:p,closeIconColorHoverError:m,closeIconColorPressedError:h})}var A={name:`Alert`,common:p,self:k},j=o(`alert`,`
 line-height: var(--n-line-height);
 border-radius: var(--n-border-radius);
 position: relative;
 transition: background-color .3s var(--n-bezier);
 background-color: var(--n-color);
 text-align: start;
 word-break: break-word;
`,[a(`border`,`
 border-radius: inherit;
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 transition: border-color .3s var(--n-bezier);
 border: var(--n-border);
 pointer-events: none;
 `),d(`closable`,[o(`alert-body`,[a(`title`,`
 padding-right: 24px;
 `)])]),a(`icon`,{color:`var(--n-icon-color)`}),o(`alert-body`,{padding:`var(--n-padding)`},[a(`title`,{color:`var(--n-title-text-color)`}),a(`content`,{color:`var(--n-content-text-color)`})]),E({originalTransition:`transform .3s var(--n-bezier)`,enterToProps:{transform:`scale(1)`},leaveToProps:{transform:`scale(0.9)`}}),a(`icon`,`
 position: absolute;
 left: 0;
 top: 0;
 align-items: center;
 justify-content: center;
 display: flex;
 width: var(--n-icon-size);
 height: var(--n-icon-size);
 font-size: var(--n-icon-size);
 margin: var(--n-icon-margin);
 `),a(`close`,`
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 position: absolute;
 right: 0;
 top: 0;
 margin: var(--n-close-margin);
 `),d(`show-icon`,[o(`alert-body`,{paddingLeft:`calc(var(--n-icon-margin-left) + var(--n-icon-size) + var(--n-icon-margin-right))`})]),d(`right-adjust`,[o(`alert-body`,{paddingRight:`calc(var(--n-close-size) + var(--n-padding) + 2px)`})]),o(`alert-body`,`
 border-radius: var(--n-border-radius);
 transition: border-color .3s var(--n-bezier);
 `,[a(`title`,`
 transition: color .3s var(--n-bezier);
 font-size: 16px;
 line-height: 19px;
 font-weight: var(--n-title-font-weight);
 `,[r(`& +`,[a(`content`,{marginTop:`9px`})])]),a(`content`,{transition:`color .3s var(--n-bezier)`,fontSize:`var(--n-font-size)`})]),a(`icon`,{transition:`color .3s var(--n-bezier)`})]),M=u({name:`Alert`,inheritAttrs:!1,props:Object.assign(Object.assign({},s.props),{title:String,showIcon:{type:Boolean,default:!0},type:{type:String,default:`default`},bordered:{type:Boolean,default:!0},closable:Boolean,onClose:Function,onAfterLeave:Function,onAfterHide:Function}),slots:Object,setup(t){let{mergedClsPrefixRef:n,mergedBorderedRef:r,inlineThemeDisabled:i,mergedRtlRef:a}=b(t),o=s(`Alert`,`-alert`,j,A,t,n),c=g(`Alert`,a,n),l=v(()=>{let{common:{cubicBezierEaseInOut:n},self:r}=o.value,{fontSize:i,borderRadius:a,titleFontWeight:s,lineHeight:c,iconSize:l,iconMargin:u,iconMarginRtl:d,closeIconSize:p,closeBorderRadius:m,closeSize:h,closeMargin:g,closeMarginRtl:_,padding:v}=r,{type:y}=t,{left:b,right:x}=e(u);return{"--n-bezier":n,"--n-color":r[f(`color`,y)],"--n-close-icon-size":p,"--n-close-border-radius":m,"--n-close-color-hover":r[f(`closeColorHover`,y)],"--n-close-color-pressed":r[f(`closeColorPressed`,y)],"--n-close-icon-color":r[f(`closeIconColor`,y)],"--n-close-icon-color-hover":r[f(`closeIconColorHover`,y)],"--n-close-icon-color-pressed":r[f(`closeIconColorPressed`,y)],"--n-icon-color":r[f(`iconColor`,y)],"--n-border":r[f(`border`,y)],"--n-title-text-color":r[f(`titleTextColor`,y)],"--n-content-text-color":r[f(`contentTextColor`,y)],"--n-line-height":c,"--n-border-radius":a,"--n-font-size":i,"--n-title-font-weight":s,"--n-icon-size":l,"--n-icon-margin":u,"--n-icon-margin-rtl":d,"--n-close-size":h,"--n-close-margin":g,"--n-close-margin-rtl":_,"--n-padding":v,"--n-icon-margin-left":b,"--n-icon-margin-right":x}}),u=i?_(`alert`,v(()=>t.type[0]),l,t):void 0,d=y(!0),p=()=>{let{onAfterLeave:e,onAfterHide:n}=t;e&&e(),n&&n()};return{rtlEnabled:c,mergedClsPrefix:n,mergedBordered:r,visible:d,handleCloseClick:()=>{Promise.resolve(t.onClose?.call(t)).then(e=>{e!==!1&&(d.value=!1)})},handleAfterLeave:()=>{p()},mergedTheme:o,cssVars:i?void 0:l,themeClass:u?.themeClass,onRender:u?.onRender}},render(){var e;return(e=this.onRender)==null||e.call(this),x(S,{onAfterLeave:this.handleAfterLeave},{default:()=>{let{mergedClsPrefix:e,$slots:n}=this,r={class:[`${e}-alert`,this.themeClass,this.closable&&`${e}-alert--closable`,this.showIcon&&`${e}-alert--show-icon`,!this.title&&this.closable&&`${e}-alert--right-adjust`,this.rtlEnabled&&`${e}-alert--rtl`],style:this.cssVars,role:`alert`};return this.visible?x(`div`,Object.assign({},c(this.$attrs,r)),this.closable&&x(l,{clsPrefix:e,class:`${e}-alert__close`,onClick:this.handleCloseClick}),this.bordered&&x(`div`,{class:`${e}-alert__border`}),this.showIcon&&x(`div`,{class:`${e}-alert__icon`,"aria-hidden":`true`},h(n.icon,()=>[x(t,{clsPrefix:e},{default:()=>{switch(this.type){case`success`:return x(C,null);case`info`:return x(w,null);case`warning`:return x(O,null);case`error`:return x(T,null);default:return null}}})])),x(`div`,{class:[`${e}-alert-body`,this.mergedBordered&&`${e}-alert-body--bordered`]},m(n.header,t=>{let n=t||this.title;return n?x(`div`,{class:`${e}-alert-body__title`},n):null}),n.default&&x(`div`,{class:`${e}-alert-body__content`},n))):null}})}});export{M as t};
//# sourceMappingURL=Alert-dluGVkos.js.map