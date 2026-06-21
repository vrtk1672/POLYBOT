import{j as t}from"./jsx-runtime-Cf8x2fCZ.js";import{S as l}from"./StatusCard-DRVIe_-s.js";import{S as p,a as s,b as i}from"./truthFixtures-BppgcTR0.js";import"./index-yBjzXJbu.js";import"./utils-DOIGBiOF.js";import"./StaleState-D9R9Cw9u.js";import"./triangle-alert-BuFKT8-3.js";import"./index-BioFo8Zg.js";import"./wrench-C-UjqXZh.js";import"./circle-slash-Cl4tLSpW.js";import"./SourceLabel-mFpV5nm0.js";import"./circle-check-DvBWHCXP.js";import"./database-Cd6ISslQ.js";const N={title:"Truth Components/Status Cards",parameters:{controls:{disable:!0}}},r={render:()=>t.jsx(p,{title:`StatusCard Truth Contract States - ${s}`,children:t.jsx("div",{className:"grid gap-4 lg:grid-cols-2",children:i.map(e=>t.jsx(l,{title:`${e.status} Fixture`,envelope:e,children:t.jsx("p",{className:"text-sm text-poly-muted",children:s})},e.status))})})};var a,o,m;r.parameters={...r.parameters,docs:{...(a=r.parameters)==null?void 0:a.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`StatusCard Truth Contract States - \${STORYBOOK_NOTICE}\`}>\r
      <div className="grid gap-4 lg:grid-cols-2">\r
        {allStatusEnvelopes.map(envelope => <StatusCard key={envelope.status} title={\`\${envelope.status} Fixture\`} envelope={envelope}>\r
            <p className="text-sm text-poly-muted">{STORYBOOK_NOTICE}</p>\r
          </StatusCard>)}\r
      </div>\r
    </StorybookFrame>
}`,...(m=(o=r.parameters)==null?void 0:o.docs)==null?void 0:m.source}}};const j=["AllTruthContractStatuses"];export{r as AllTruthContractStatuses,j as __namedExportsOrder,N as default};
