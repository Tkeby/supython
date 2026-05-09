import{At as e,Bt as t,Ft as n,Gt as r,Jt as i,Kt as a,Ln as o,O as s,S as c,Sn as l,Xt as u,Yt as d,Zt as f,_ as p,_t as m,ar as h,j as g,lt as _,mn as v,tr as y,ut as b,wn as x,wt as S,xt as C}from"./Space-n5-XcguU.js";function w(e,t){return v(()=>{for(let n of t)if(e[n]!==void 0)return e[n];return e[t[t.length-1]]})}var T={closeIconSizeTiny:`12px`,closeIconSizeSmall:`12px`,closeIconSizeMedium:`14px`,closeIconSizeLarge:`14px`,closeSizeTiny:`16px`,closeSizeSmall:`16px`,closeSizeMedium:`18px`,closeSizeLarge:`18px`,padding:`0 7px`,closeMargin:`0 0 0 4px`};function E(e){let{textColor2:t,primaryColorHover:r,primaryColorPressed:i,primaryColor:a,infoColor:o,successColor:s,warningColor:c,errorColor:l,baseColor:u,borderColor:d,opacityDisabled:f,tagColor:p,closeIconColor:m,closeIconColorHover:h,closeIconColorPressed:g,borderRadiusSmall:_,fontSizeMini:v,fontSizeTiny:y,fontSizeSmall:b,fontSizeMedium:x,heightMini:S,heightTiny:C,heightSmall:w,heightMedium:E,closeColorHover:D,closeColorPressed:O,buttonColor2Hover:k,buttonColor2Pressed:A,fontWeightStrong:j}=e;return Object.assign(Object.assign({},T),{closeBorderRadius:_,heightTiny:S,heightSmall:C,heightMedium:w,heightLarge:E,borderRadius:_,opacityDisabled:f,fontSizeTiny:v,fontSizeSmall:y,fontSizeMedium:b,fontSizeLarge:x,fontWeightStrong:j,textColorCheckable:t,textColorHoverCheckable:t,textColorPressedCheckable:t,textColorChecked:u,colorCheckable:`#0000`,colorHoverCheckable:k,colorPressedCheckable:A,colorChecked:a,colorCheckedHover:r,colorCheckedPressed:i,border:`1px solid ${d}`,textColor:t,color:p,colorBordered:`rgb(250, 250, 252)`,closeIconColor:m,closeIconColorHover:h,closeIconColorPressed:g,closeColorHover:D,closeColorPressed:O,borderPrimary:`1px solid ${n(a,{alpha:.3})}`,textColorPrimary:a,colorPrimary:n(a,{alpha:.12}),colorBorderedPrimary:n(a,{alpha:.1}),closeIconColorPrimary:a,closeIconColorHoverPrimary:a,closeIconColorPressedPrimary:a,closeColorHoverPrimary:n(a,{alpha:.12}),closeColorPressedPrimary:n(a,{alpha:.18}),borderInfo:`1px solid ${n(o,{alpha:.3})}`,textColorInfo:o,colorInfo:n(o,{alpha:.12}),colorBorderedInfo:n(o,{alpha:.1}),closeIconColorInfo:o,closeIconColorHoverInfo:o,closeIconColorPressedInfo:o,closeColorHoverInfo:n(o,{alpha:.12}),closeColorPressedInfo:n(o,{alpha:.18}),borderSuccess:`1px solid ${n(s,{alpha:.3})}`,textColorSuccess:s,colorSuccess:n(s,{alpha:.12}),colorBorderedSuccess:n(s,{alpha:.1}),closeIconColorSuccess:s,closeIconColorHoverSuccess:s,closeIconColorPressedSuccess:s,closeColorHoverSuccess:n(s,{alpha:.12}),closeColorPressedSuccess:n(s,{alpha:.18}),borderWarning:`1px solid ${n(c,{alpha:.35})}`,textColorWarning:c,colorWarning:n(c,{alpha:.15}),colorBorderedWarning:n(c,{alpha:.12}),closeIconColorWarning:c,closeIconColorHoverWarning:c,closeIconColorPressedWarning:c,closeColorHoverWarning:n(c,{alpha:.12}),closeColorPressedWarning:n(c,{alpha:.18}),borderError:`1px solid ${n(l,{alpha:.23})}`,textColorError:l,colorError:n(l,{alpha:.1}),colorBorderedError:n(l,{alpha:.08}),closeIconColorError:l,closeIconColorHoverError:l,closeIconColorPressedError:l,closeColorHoverError:n(l,{alpha:.12}),closeColorPressedError:n(l,{alpha:.18})})}var D={name:`Tag`,common:p,self:E},O={color:Object,type:{type:String,default:`default`},round:Boolean,size:String,closable:Boolean,disabled:{type:Boolean,default:void 0}},k=a(`tag`,`
 --n-close-margin: var(--n-close-margin-top) var(--n-close-margin-right) var(--n-close-margin-bottom) var(--n-close-margin-left);
 white-space: nowrap;
 position: relative;
 box-sizing: border-box;
 cursor: default;
 display: inline-flex;
 align-items: center;
 flex-wrap: nowrap;
 padding: var(--n-padding);
 border-radius: var(--n-border-radius);
 color: var(--n-text-color);
 background-color: var(--n-color);
 transition: 
 border-color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 line-height: 1;
 height: var(--n-height);
 font-size: var(--n-font-size);
`,[d(`strong`,`
 font-weight: var(--n-font-weight-strong);
 `),i(`border`,`
 pointer-events: none;
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 border-radius: inherit;
 border: var(--n-border);
 transition: border-color .3s var(--n-bezier);
 `),i(`icon`,`
 display: flex;
 margin: 0 4px 0 0;
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 font-size: var(--n-avatar-size-override);
 `),i(`avatar`,`
 display: flex;
 margin: 0 6px 0 0;
 `),i(`close`,`
 margin: var(--n-close-margin);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `),d(`round`,`
 padding: 0 calc(var(--n-height) / 3);
 border-radius: calc(var(--n-height) / 2);
 `,[i(`icon`,`
 margin: 0 4px 0 calc((var(--n-height) - 8px) / -2);
 `),i(`avatar`,`
 margin: 0 6px 0 calc((var(--n-height) - 8px) / -2);
 `),d(`closable`,`
 padding: 0 calc(var(--n-height) / 4) 0 calc(var(--n-height) / 3);
 `)]),d(`icon, avatar`,[d(`round`,`
 padding: 0 calc(var(--n-height) / 3) 0 calc(var(--n-height) / 2);
 `)]),d(`disabled`,`
 cursor: not-allowed !important;
 opacity: var(--n-opacity-disabled);
 `),d(`checkable`,`
 cursor: pointer;
 box-shadow: none;
 color: var(--n-text-color-checkable);
 background-color: var(--n-color-checkable);
 `,[u(`disabled`,[r(`&:hover`,`background-color: var(--n-color-hover-checkable);`,[u(`checked`,`color: var(--n-text-color-hover-checkable);`)]),r(`&:active`,`background-color: var(--n-color-pressed-checkable);`,[u(`checked`,`color: var(--n-text-color-pressed-checkable);`)])]),d(`checked`,`
 color: var(--n-text-color-checked);
 background-color: var(--n-color-checked);
 `,[u(`disabled`,[r(`&:hover`,`background-color: var(--n-color-checked-hover);`),r(`&:active`,`background-color: var(--n-color-checked-pressed);`)])])])]),A=Object.assign(Object.assign(Object.assign({},s.props),O),{bordered:{type:Boolean,default:void 0},checked:Boolean,checkable:Boolean,strong:Boolean,triggerClickOnClose:Boolean,onClose:[Array,Function],onMouseenter:Function,onMouseleave:Function,"onUpdate:checked":Function,onUpdateChecked:Function,internalCloseFocusable:{type:Boolean,default:!0},internalCloseIsButtonTag:{type:Boolean,default:!0},onCheckedChange:Function}),j=e(`n-tag`),M=l({name:`Tag`,props:A,slots:Object,setup(e){let n=y(null),{mergedBorderedRef:r,mergedClsPrefixRef:i,inlineThemeDisabled:a,mergedRtlRef:c,mergedComponentPropsRef:l}=b(e),u=v(()=>e.size||l?.value?.Tag?.size||`medium`),d=s(`Tag`,`-tag`,k,D,e,i);o(j,{roundRef:h(e,`round`)});function p(){if(!e.disabled&&e.checkable){let{checked:t,onCheckedChange:n,onUpdateChecked:r,"onUpdate:checked":i}=e;r&&r(!t),i&&i(!t),n&&n(!t)}}function m(t){if(e.triggerClickOnClose||t.stopPropagation(),!e.disabled){let{onClose:n}=e;n&&C(n,t)}}let x={setTextContent(e){let{value:t}=n;t&&(t.textContent=e)}},w=g(`Tag`,c,i),T=v(()=>{let{type:n,color:{color:i,textColor:a}={}}=e,o=u.value,{common:{cubicBezierEaseInOut:s},self:{padding:c,closeMargin:l,borderRadius:p,opacityDisabled:m,textColorCheckable:h,textColorHoverCheckable:g,textColorPressedCheckable:_,textColorChecked:v,colorCheckable:y,colorHoverCheckable:b,colorPressedCheckable:x,colorChecked:S,colorCheckedHover:C,colorCheckedPressed:w,closeBorderRadius:T,fontWeightStrong:E,[f(`colorBordered`,n)]:D,[f(`closeSize`,o)]:O,[f(`closeIconSize`,o)]:k,[f(`fontSize`,o)]:A,[f(`height`,o)]:j,[f(`color`,n)]:M,[f(`textColor`,n)]:N,[f(`border`,n)]:P,[f(`closeIconColor`,n)]:F,[f(`closeIconColorHover`,n)]:I,[f(`closeIconColorPressed`,n)]:L,[f(`closeColorHover`,n)]:R,[f(`closeColorPressed`,n)]:z}}=d.value,B=t(l);return{"--n-font-weight-strong":E,"--n-avatar-size-override":`calc(${j} - 8px)`,"--n-bezier":s,"--n-border-radius":p,"--n-border":P,"--n-close-icon-size":k,"--n-close-color-pressed":z,"--n-close-color-hover":R,"--n-close-border-radius":T,"--n-close-icon-color":F,"--n-close-icon-color-hover":I,"--n-close-icon-color-pressed":L,"--n-close-icon-color-disabled":F,"--n-close-margin-top":B.top,"--n-close-margin-right":B.right,"--n-close-margin-bottom":B.bottom,"--n-close-margin-left":B.left,"--n-close-size":O,"--n-color":i||(r.value?D:M),"--n-color-checkable":y,"--n-color-checked":S,"--n-color-checked-hover":C,"--n-color-checked-pressed":w,"--n-color-hover-checkable":b,"--n-color-pressed-checkable":x,"--n-font-size":A,"--n-height":j,"--n-opacity-disabled":m,"--n-padding":c,"--n-text-color":a||N,"--n-text-color-checkable":h,"--n-text-color-checked":v,"--n-text-color-hover-checkable":g,"--n-text-color-pressed-checkable":_}}),E=a?_(`tag`,v(()=>{let t=``,{type:n,color:{color:i,textColor:a}={}}=e;return t+=n[0],t+=u.value[0],i&&(t+=`a${S(i)}`),a&&(t+=`b${S(a)}`),r.value&&(t+=`c`),t}),T,e):void 0;return Object.assign(Object.assign({},x),{rtlEnabled:w,mergedClsPrefix:i,contentRef:n,mergedBordered:r,handleClick:p,handleCloseClick:m,cssVars:a?void 0:T,themeClass:E?.themeClass,onRender:E?.onRender})},render(){var e;let{mergedClsPrefix:t,rtlEnabled:n,closable:r,color:{borderColor:i}={},round:a,onRender:o,$slots:s}=this;o?.();let l=m(s.avatar,e=>e&&x(`div`,{class:`${t}-tag__avatar`},e)),u=m(s.icon,e=>e&&x(`div`,{class:`${t}-tag__icon`},e));return x(`div`,{class:[`${t}-tag`,this.themeClass,{[`${t}-tag--rtl`]:n,[`${t}-tag--strong`]:this.strong,[`${t}-tag--disabled`]:this.disabled,[`${t}-tag--checkable`]:this.checkable,[`${t}-tag--checked`]:this.checkable&&this.checked,[`${t}-tag--round`]:a,[`${t}-tag--avatar`]:l,[`${t}-tag--icon`]:u,[`${t}-tag--closable`]:r}],style:this.cssVars,onClick:this.handleClick,onMouseenter:this.onMouseenter,onMouseleave:this.onMouseleave},u||l,x(`span`,{class:`${t}-tag__content`,ref:`contentRef`},(e=this.$slots).default?.call(e)),!this.checkable&&r?x(c,{clsPrefix:t,class:`${t}-tag__close`,disabled:this.disabled,onClick:this.handleCloseClick,focusable:this.internalCloseFocusable,round:a,isButtonTag:this.internalCloseIsButtonTag,absolute:!0}):null,!this.checkable&&this.mergedBordered?x(`div`,{class:`${t}-tag__border`,style:{borderColor:i}}):null)}});export{T as n,w as r,M as t};
//# sourceMappingURL=Tag-D1fOKpTH.js.map