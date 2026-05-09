import{$t as e,Gt as t,Jt as n,Kt as r,O as i,Qt as a,Sn as o,Xt as s,Yt as c,Zt as l,bt as u,lt as d,mn as f,ut as p,wn as m,yt as h}from"./Space-n5-XcguU.js";import{s as g}from"./Input-DppYTq9C.js";import{r as _}from"./Tag-D1fOKpTH.js";import{x as v}from"./index-CeE6v959.js";function y(e,t=`default`,n=[]){let{children:r}=e;if(typeof r==`object`&&r&&!Array.isArray(r)){let e=r[t];if(typeof e==`function`)return e()}return n}var b=t([r(`descriptions`,{fontSize:`var(--n-font-size)`},[r(`descriptions-separator`,`
 display: inline-block;
 margin: 0 8px 0 2px;
 `),r(`descriptions-table-wrapper`,[r(`descriptions-table`,[r(`descriptions-table-row`,[r(`descriptions-table-header`,{padding:`var(--n-th-padding)`}),r(`descriptions-table-content`,{padding:`var(--n-td-padding)`})])])]),s(`bordered`,[r(`descriptions-table-wrapper`,[r(`descriptions-table`,[r(`descriptions-table-row`,[t(`&:last-child`,[r(`descriptions-table-content`,{paddingBottom:0})])])])])]),c(`left-label-placement`,[r(`descriptions-table-content`,[t(`> *`,{verticalAlign:`top`})])]),c(`left-label-align`,[t(`th`,{textAlign:`left`})]),c(`center-label-align`,[t(`th`,{textAlign:`center`})]),c(`right-label-align`,[t(`th`,{textAlign:`right`})]),c(`bordered`,[r(`descriptions-table-wrapper`,`
 border-radius: var(--n-border-radius);
 overflow: hidden;
 background: var(--n-merged-td-color);
 border: 1px solid var(--n-merged-border-color);
 `,[r(`descriptions-table`,[r(`descriptions-table-row`,[t(`&:not(:last-child)`,[r(`descriptions-table-content`,{borderBottom:`1px solid var(--n-merged-border-color)`}),r(`descriptions-table-header`,{borderBottom:`1px solid var(--n-merged-border-color)`})]),r(`descriptions-table-header`,`
 font-weight: 400;
 background-clip: padding-box;
 background-color: var(--n-merged-th-color);
 `,[t(`&:not(:last-child)`,{borderRight:`1px solid var(--n-merged-border-color)`})]),r(`descriptions-table-content`,[t(`&:not(:last-child)`,{borderRight:`1px solid var(--n-merged-border-color)`})])])])])]),r(`descriptions-header`,`
 font-weight: var(--n-th-font-weight);
 font-size: 18px;
 transition: color .3s var(--n-bezier);
 line-height: var(--n-line-height);
 margin-bottom: 16px;
 color: var(--n-title-text-color);
 `),r(`descriptions-table-wrapper`,`
 transition:
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[r(`descriptions-table`,`
 width: 100%;
 border-collapse: separate;
 border-spacing: 0;
 box-sizing: border-box;
 `,[r(`descriptions-table-row`,`
 box-sizing: border-box;
 transition: border-color .3s var(--n-bezier);
 `,[r(`descriptions-table-header`,`
 font-weight: var(--n-th-font-weight);
 line-height: var(--n-line-height);
 display: table-cell;
 box-sizing: border-box;
 color: var(--n-th-text-color);
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `),r(`descriptions-table-content`,`
 vertical-align: top;
 line-height: var(--n-line-height);
 display: table-cell;
 box-sizing: border-box;
 color: var(--n-td-text-color);
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[n(`content`,`
 transition: color .3s var(--n-bezier);
 display: inline-block;
 color: var(--n-td-text-color);
 `)]),n(`label`,`
 font-weight: var(--n-th-font-weight);
 transition: color .3s var(--n-bezier);
 display: inline-block;
 margin-right: 14px;
 color: var(--n-th-text-color);
 `)])])])]),r(`descriptions-table-wrapper`,`
 --n-merged-th-color: var(--n-th-color);
 --n-merged-td-color: var(--n-td-color);
 --n-merged-border-color: var(--n-border-color);
 `),a(r(`descriptions-table-wrapper`,`
 --n-merged-th-color: var(--n-th-color-modal);
 --n-merged-td-color: var(--n-td-color-modal);
 --n-merged-border-color: var(--n-border-color-modal);
 `)),e(r(`descriptions-table-wrapper`,`
 --n-merged-th-color: var(--n-th-color-popover);
 --n-merged-td-color: var(--n-td-color-popover);
 --n-merged-border-color: var(--n-border-color-popover);
 `))]),x=`DESCRIPTION_ITEM_FLAG`;function S(e){return typeof e==`object`&&e&&!Array.isArray(e)?e.type&&e.type.DESCRIPTION_ITEM_FLAG:!1}var C=o({name:`Descriptions`,props:Object.assign(Object.assign({},i.props),{title:String,column:{type:Number,default:3},columns:Number,labelPlacement:{type:String,default:`top`},labelAlign:{type:String,default:`left`},separator:{type:String,default:`:`},size:String,bordered:Boolean,labelClass:String,labelStyle:[Object,String],contentClass:String,contentStyle:[Object,String]}),slots:Object,setup(e){let{mergedClsPrefixRef:t,inlineThemeDisabled:n,mergedComponentPropsRef:r}=p(e),a=f(()=>e.size||r?.value?.Descriptions?.size||`medium`),o=i(`Descriptions`,`-descriptions`,b,v,e,t),s=f(()=>{let{bordered:t}=e,n=a.value,{common:{cubicBezierEaseInOut:r},self:{titleTextColor:i,thColor:s,thColorModal:c,thColorPopover:u,thTextColor:d,thFontWeight:f,tdTextColor:p,tdColor:m,tdColorModal:h,tdColorPopover:g,borderColor:_,borderColorModal:v,borderColorPopover:y,borderRadius:b,lineHeight:x,[l(`fontSize`,n)]:S,[l(t?`thPaddingBordered`:`thPadding`,n)]:C,[l(t?`tdPaddingBordered`:`tdPadding`,n)]:w}}=o.value;return{"--n-title-text-color":i,"--n-th-padding":C,"--n-td-padding":w,"--n-font-size":S,"--n-bezier":r,"--n-th-font-weight":f,"--n-line-height":x,"--n-th-text-color":d,"--n-td-text-color":p,"--n-th-color":s,"--n-th-color-modal":c,"--n-th-color-popover":u,"--n-td-color":m,"--n-td-color-modal":h,"--n-td-color-popover":g,"--n-border-radius":b,"--n-border-color":_,"--n-border-color-modal":v,"--n-border-color-popover":y}}),c=n?d(`descriptions`,f(()=>{let t=``,{bordered:n}=e;return n&&(t+=`a`),t+=a.value[0],t}),s,e):void 0;return{mergedClsPrefix:t,cssVars:n?void 0:s,themeClass:c?.themeClass,onRender:c?.onRender,compitableColumn:_(e,[`columns`,`column`]),inlineThemeDisabled:n,mergedSize:a}},render(){let e=this.$slots.default,t=e?u(e()):[];t.length;let{contentClass:n,labelClass:r,compitableColumn:i,labelPlacement:a,labelAlign:o,mergedSize:s,bordered:c,title:l,cssVars:d,mergedClsPrefix:f,separator:p,onRender:_}=this;_?.();let v=t.filter(e=>S(e)),b=v.reduce((e,t,o)=>{let s=t.props||{},l=v.length-1===o,u=[`label`in s?s.label:y(t,`label`)],d=[y(t)],h=s.span||1,g=e.span;e.span+=h;let _=s.labelStyle||s[`label-style`]||this.labelStyle,b=s.contentStyle||s[`content-style`]||this.contentStyle;if(a===`left`)c?e.row.push(m(`th`,{class:[`${f}-descriptions-table-header`,r],colspan:1,style:_},u),m(`td`,{class:[`${f}-descriptions-table-content`,n],colspan:l?(i-g)*2+1:h*2-1,style:b},d)):e.row.push(m(`td`,{class:`${f}-descriptions-table-content`,colspan:l?(i-g)*2:h*2},m(`span`,{class:[`${f}-descriptions-table-content__label`,r],style:_},[...u,p&&m(`span`,{class:`${f}-descriptions-separator`},p)]),m(`span`,{class:[`${f}-descriptions-table-content__content`,n],style:b},d)));else{let t=l?(i-g)*2:h*2;e.row.push(m(`th`,{class:[`${f}-descriptions-table-header`,r],colspan:t,style:_},u)),e.secondRow.push(m(`td`,{class:[`${f}-descriptions-table-content`,n],colspan:t,style:b},d))}return(e.span>=i||l)&&(e.span=0,e.row.length&&(e.rows.push(e.row),e.row=[]),a!==`left`&&e.secondRow.length&&(e.rows.push(e.secondRow),e.secondRow=[])),e},{span:0,row:[],secondRow:[],rows:[]}).rows.map(e=>m(`tr`,{class:`${f}-descriptions-table-row`},e));return m(`div`,{style:d,class:[`${f}-descriptions`,this.themeClass,`${f}-descriptions--${a}-label-placement`,`${f}-descriptions--${o}-label-align`,`${f}-descriptions--${s}-size`,c&&`${f}-descriptions--bordered`]},l||this.$slots.header?m(`div`,{class:`${f}-descriptions-header`},l||h(this,`header`)):null,m(`div`,{class:`${f}-descriptions-table-wrapper`},m(`table`,{class:`${f}-descriptions-table`},m(`tbody`,null,a===`top`&&m(`tr`,{class:`${f}-descriptions-table-row`,style:{visibility:`collapse`}},g(i*2,m(`td`,null))),b))))}}),w={label:String,span:{type:Number,default:1},labelClass:String,labelStyle:[Object,String],contentClass:String,contentStyle:[Object,String]},T=o({name:`DescriptionsItem`,[x]:!0,props:w,slots:Object,render(){return null}});export{C as n,T as t};
//# sourceMappingURL=DescriptionsItem-P8JUDaBs.js.map