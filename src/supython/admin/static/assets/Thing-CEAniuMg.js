import{$t as e,At as t,En as n,Gt as r,Jt as i,Kt as a,Ln as o,O as s,Qt as c,Sn as l,St as u,Yt as d,ar as f,j as p,lt as m,mn as h,un as g,ut as _,wn as v}from"./Space-n5-XcguU.js";import{f as y,g as b}from"./index-CeE6v959.js";var x=r([a(`list`,`
 --n-merged-border-color: var(--n-border-color);
 --n-merged-color: var(--n-color);
 --n-merged-color-hover: var(--n-color-hover);
 margin: 0;
 font-size: var(--n-font-size);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 padding: 0;
 list-style-type: none;
 color: var(--n-text-color);
 background-color: var(--n-merged-color);
 `,[d(`show-divider`,[a(`list-item`,[r(`&:not(:last-child)`,[i(`divider`,`
 background-color: var(--n-merged-border-color);
 `)])])]),d(`clickable`,[a(`list-item`,`
 cursor: pointer;
 `)]),d(`bordered`,`
 border: 1px solid var(--n-merged-border-color);
 border-radius: var(--n-border-radius);
 `),d(`hoverable`,[a(`list-item`,`
 border-radius: var(--n-border-radius);
 `,[r(`&:hover`,`
 background-color: var(--n-merged-color-hover);
 `,[i(`divider`,`
 background-color: transparent;
 `)])])]),d(`bordered, hoverable`,[a(`list-item`,`
 padding: 12px 20px;
 `),i(`header, footer`,`
 padding: 12px 20px;
 `)]),i(`header, footer`,`
 padding: 12px 0;
 box-sizing: border-box;
 transition: border-color .3s var(--n-bezier);
 `,[r(`&:not(:last-child)`,`
 border-bottom: 1px solid var(--n-merged-border-color);
 `)]),a(`list-item`,`
 position: relative;
 padding: 12px 0; 
 box-sizing: border-box;
 display: flex;
 flex-wrap: nowrap;
 align-items: center;
 transition:
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[i(`prefix`,`
 margin-right: 20px;
 flex: 0;
 `),i(`suffix`,`
 margin-left: 20px;
 flex: 0;
 `),i(`main`,`
 flex: 1;
 `),i(`divider`,`
 height: 1px;
 position: absolute;
 bottom: 0;
 left: 0;
 right: 0;
 background-color: transparent;
 transition: background-color .3s var(--n-bezier);
 pointer-events: none;
 `)])]),c(a(`list`,`
 --n-merged-color-hover: var(--n-color-hover-modal);
 --n-merged-color: var(--n-color-modal);
 --n-merged-border-color: var(--n-border-color-modal);
 `)),e(a(`list`,`
 --n-merged-color-hover: var(--n-color-hover-popover);
 --n-merged-color: var(--n-color-popover);
 --n-merged-border-color: var(--n-border-color-popover);
 `))]),S=Object.assign(Object.assign({},s.props),{size:{type:String,default:`medium`},bordered:Boolean,clickable:Boolean,hoverable:Boolean,showDivider:{type:Boolean,default:!0}}),C=t(`n-list`),w=l({name:`List`,props:S,slots:Object,setup(e){let{mergedClsPrefixRef:t,inlineThemeDisabled:n,mergedRtlRef:r}=_(e),i=p(`List`,r,t),a=s(`List`,`-list`,x,b,e,t);o(C,{showDividerRef:f(e,`showDivider`),mergedClsPrefixRef:t});let c=h(()=>{let{common:{cubicBezierEaseInOut:e},self:{fontSize:t,textColor:n,color:r,colorModal:i,colorPopover:o,borderColor:s,borderColorModal:c,borderColorPopover:l,borderRadius:u,colorHover:d,colorHoverModal:f,colorHoverPopover:p}}=a.value;return{"--n-font-size":t,"--n-bezier":e,"--n-text-color":n,"--n-color":r,"--n-border-radius":u,"--n-border-color":s,"--n-border-color-modal":c,"--n-border-color-popover":l,"--n-color-modal":i,"--n-color-popover":o,"--n-color-hover":d,"--n-color-hover-modal":f,"--n-color-hover-popover":p}}),l=n?m(`list`,void 0,c,e):void 0;return{mergedClsPrefix:t,rtlEnabled:i,cssVars:n?void 0:c,themeClass:l?.themeClass,onRender:l?.onRender}},render(){let{$slots:e,mergedClsPrefix:t,onRender:n}=this;return n?.(),v(`ul`,{class:[`${t}-list`,this.rtlEnabled&&`${t}-list--rtl`,this.bordered&&`${t}-list--bordered`,this.showDivider&&`${t}-list--show-divider`,this.hoverable&&`${t}-list--hoverable`,this.clickable&&`${t}-list--clickable`,this.themeClass],style:this.cssVars},e.header?v(`div`,{class:`${t}-list__header`},e.header()):null,e.default?.call(e),e.footer?v(`div`,{class:`${t}-list__footer`},e.footer()):null)}}),T=l({name:`ListItem`,slots:Object,setup(){let e=n(C,null);return e||u(`list-item`,"`n-list-item` must be placed in `n-list`."),{showDivider:e.showDividerRef,mergedClsPrefix:e.mergedClsPrefixRef}},render(){let{$slots:e,mergedClsPrefix:t}=this;return v(`li`,{class:`${t}-list-item`},e.prefix?v(`div`,{class:`${t}-list-item__prefix`},e.prefix()):null,e.default?v(`div`,{class:`${t}-list-item__main`},e):null,e.suffix?v(`div`,{class:`${t}-list-item__suffix`},e.suffix()):null,this.showDivider&&v(`div`,{class:`${t}-list-item__divider`}))}}),E=a(`thing`,`
 display: flex;
 transition: color .3s var(--n-bezier);
 font-size: var(--n-font-size);
 color: var(--n-text-color);
`,[a(`thing-avatar`,`
 margin-right: 12px;
 margin-top: 2px;
 `),a(`thing-avatar-header-wrapper`,`
 display: flex;
 flex-wrap: nowrap;
 `,[a(`thing-header-wrapper`,`
 flex: 1;
 `)]),a(`thing-main`,`
 flex-grow: 1;
 `,[a(`thing-header`,`
 display: flex;
 margin-bottom: 4px;
 justify-content: space-between;
 align-items: center;
 `,[i(`title`,`
 font-size: 16px;
 font-weight: var(--n-title-font-weight);
 transition: color .3s var(--n-bezier);
 color: var(--n-title-text-color);
 `)]),i(`description`,[r(`&:not(:last-child)`,`
 margin-bottom: 4px;
 `)]),i(`content`,[r(`&:not(:first-child)`,`
 margin-top: 12px;
 `)]),i(`footer`,[r(`&:not(:first-child)`,`
 margin-top: 12px;
 `)]),i(`action`,[r(`&:not(:first-child)`,`
 margin-top: 12px;
 `)])])]),D=l({name:`Thing`,props:Object.assign(Object.assign({},s.props),{title:String,titleExtra:String,description:String,descriptionClass:String,descriptionStyle:[String,Object],content:String,contentClass:String,contentStyle:[String,Object],contentIndented:Boolean}),slots:Object,setup(e,{slots:t}){let{mergedClsPrefixRef:n,inlineThemeDisabled:r,mergedRtlRef:i}=_(e),a=s(`Thing`,`-thing`,E,y,e,n),o=p(`Thing`,i,n),c=h(()=>{let{self:{titleTextColor:e,textColor:t,titleFontWeight:n,fontSize:r},common:{cubicBezierEaseInOut:i}}=a.value;return{"--n-bezier":i,"--n-font-size":r,"--n-text-color":t,"--n-title-font-weight":n,"--n-title-text-color":e}}),l=r?m(`thing`,void 0,c,e):void 0;return()=>{var i;let{value:a}=n,s=o?o.value:!1;return(i=l?.onRender)==null||i.call(l),v(`div`,{class:[`${a}-thing`,l?.themeClass,s&&`${a}-thing--rtl`],style:r?void 0:c.value},t.avatar&&e.contentIndented?v(`div`,{class:`${a}-thing-avatar`},t.avatar()):null,v(`div`,{class:`${a}-thing-main`},!e.contentIndented&&(t.header||e.title||t[`header-extra`]||e.titleExtra||t.avatar)?v(`div`,{class:`${a}-thing-avatar-header-wrapper`},t.avatar?v(`div`,{class:`${a}-thing-avatar`},t.avatar()):null,t.header||e.title||t[`header-extra`]||e.titleExtra?v(`div`,{class:`${a}-thing-header-wrapper`},v(`div`,{class:`${a}-thing-header`},t.header||e.title?v(`div`,{class:`${a}-thing-header__title`},t.header?t.header():e.title):null,t[`header-extra`]||e.titleExtra?v(`div`,{class:`${a}-thing-header__extra`},t[`header-extra`]?t[`header-extra`]():e.titleExtra):null),t.description||e.description?v(`div`,{class:[`${a}-thing-main__description`,e.descriptionClass],style:e.descriptionStyle},t.description?t.description():e.description):null):null):v(g,null,t.header||e.title||t[`header-extra`]||e.titleExtra?v(`div`,{class:`${a}-thing-header`},t.header||e.title?v(`div`,{class:`${a}-thing-header__title`},t.header?t.header():e.title):null,t[`header-extra`]||e.titleExtra?v(`div`,{class:`${a}-thing-header__extra`},t[`header-extra`]?t[`header-extra`]():e.titleExtra):null):null,t.description||e.description?v(`div`,{class:[`${a}-thing-main__description`,e.descriptionClass],style:e.descriptionStyle},t.description?t.description():e.description):null),t.default||e.content?v(`div`,{class:[`${a}-thing-main__content`,e.contentClass],style:e.contentStyle},t.default?t.default():e.content):null,t.footer?v(`div`,{class:`${a}-thing-main__footer`},t.footer()):null,t.action?v(`div`,{class:`${a}-thing-main__action`},t.action()):null))}}});export{T as n,w as r,D as t};
//# sourceMappingURL=Thing-CEAniuMg.js.map