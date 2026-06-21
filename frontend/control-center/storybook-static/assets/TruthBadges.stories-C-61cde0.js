import{j as e}from"./jsx-runtime-Cf8x2fCZ.js";import{F as g,S as n,T as x}from"./SourceLabel-mFpV5nm0.js";import{S as o,a as l,c as T}from"./truthFixtures-BppgcTR0.js";import"./index-yBjzXJbu.js";import"./utils-DOIGBiOF.js";import"./circle-slash-Cl4tLSpW.js";import"./triangle-alert-BuFKT8-3.js";import"./index-BioFo8Zg.js";import"./wrench-C-UjqXZh.js";import"./circle-check-DvBWHCXP.js";import"./database-Cd6ISslQ.js";const k={title:"Truth Components/Badges",parameters:{controls:{disable:!0}}},h=["REAL","STALE","MISSING","ERROR","LOCKED","NOT_IMPLEMENTED","PARTIAL"],y=["ACTIVE_FRESH","LAST_KNOWN","HISTORICAL_ONLY","REFRESH_REQUIRED","UNKNOWN"],s={render:()=>e.jsx(o,{title:`TruthBadge States - ${l}`,children:e.jsx("div",{className:"flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4",children:h.map(r=>e.jsx(x,{status:r},r))})})},a={render:()=>e.jsx(o,{title:`FreshnessBadge States - ${l}`,children:e.jsx("div",{className:"flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4",children:y.map(r=>e.jsx(g,{truthState:r},r))})})},t={render:()=>e.jsx(o,{title:`SourceLabel States - ${l}`,children:e.jsxs("div",{className:"flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4",children:[e.jsx(n,{source:T}),e.jsx(n,{source:null})]})})};var p,d,c;s.parameters={...s.parameters,docs:{...(p=s.parameters)==null?void 0:p.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`TruthBadge States - \${STORYBOOK_NOTICE}\`}>\r
      <div className="flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4">\r
        {statuses.map(status => <TruthBadge key={status} status={status} />)}\r
      </div>\r
    </StorybookFrame>
}`,...(c=(d=s.parameters)==null?void 0:d.docs)==null?void 0:c.source}}};var u,S,m;a.parameters={...a.parameters,docs:{...(u=a.parameters)==null?void 0:u.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`FreshnessBadge States - \${STORYBOOK_NOTICE}\`}>\r
      <div className="flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4">\r
        {truthStates.map(truthState => <FreshnessBadge key={truthState} truthState={truthState} />)}\r
      </div>\r
    </StorybookFrame>
}`,...(m=(S=a.parameters)==null?void 0:S.docs)==null?void 0:m.source}}};var i,b,O;t.parameters={...t.parameters,docs:{...(i=t.parameters)==null?void 0:i.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`SourceLabel States - \${STORYBOOK_NOTICE}\`}>\r
      <div className="flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4">\r
        <SourceLabel source={STORYBOOK_SOURCE} />\r
        <SourceLabel source={null} />\r
      </div>\r
    </StorybookFrame>
}`,...(O=(b=t.parameters)==null?void 0:b.docs)==null?void 0:O.source}}};const v=["TruthStatuses","FreshnessStates","SourceLabels"];export{a as FreshnessStates,t as SourceLabels,s as TruthStatuses,v as __namedExportsOrder,k as default};
