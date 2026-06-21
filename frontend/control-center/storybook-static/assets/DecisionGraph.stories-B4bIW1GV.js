import{j as e}from"./jsx-runtime-Cf8x2fCZ.js";import{D as t}from"./DecisionGraph-GOwm4eZ8.js";import{S as n,a as s,m as f,l as k,r as G,d as b}from"./truthFixtures-BppgcTR0.js";import"./index-yBjzXJbu.js";import"./index-BioFo8Zg.js";import"./index-CncNTZwy.js";import"./index-B6ujFmsw.js";/* empty css              */import"./visibilityUtils-B12rpEXr.js";import"./utils-DOIGBiOF.js";const w={title:"Visibility Pages/Stage 12 React Flow",parameters:{controls:{disable:!0}}},r={render:()=>e.jsx(n,{title:`Decision Graph - ${s}`,children:e.jsx(t,{kind:"decision-xray",envelope:b})})},o={render:()=>e.jsx(n,{title:`Conflict Map - ${s}`,children:e.jsx(t,{kind:"conflict-map",envelope:G})})},a={render:()=>e.jsx(n,{title:`Candidate Lifecycle - ${s}`,children:e.jsx(t,{kind:"candidate-lifecycle",envelope:k})})},i={render:()=>e.jsx(n,{title:`Brain Flow Empty State - ${s}`,children:e.jsx(t,{kind:"brain-flow",envelope:f})})};var c,p,l;r.parameters={...r.parameters,docs:{...(c=r.parameters)==null?void 0:c.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`Decision Graph - \${STORYBOOK_NOTICE}\`}>\r
      <DecisionGraph kind="decision-xray" envelope={decisionXrayFixture} />\r
    </StorybookFrame>
}`,...(l=(p=r.parameters)==null?void 0:p.docs)==null?void 0:l.source}}};var d,m,y;o.parameters={...o.parameters,docs:{...(d=o.parameters)==null?void 0:d.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`Conflict Map - \${STORYBOOK_NOTICE}\`}>\r
      <DecisionGraph kind="conflict-map" envelope={riskEvidenceFixture} />\r
    </StorybookFrame>
}`,...(y=(m=o.parameters)==null?void 0:m.docs)==null?void 0:y.source}}};var u,x,F;a.parameters={...a.parameters,docs:{...(u=a.parameters)==null?void 0:u.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`Candidate Lifecycle - \${STORYBOOK_NOTICE}\`}>\r
      <DecisionGraph kind="candidate-lifecycle" envelope={lifecycleFixture} />\r
    </StorybookFrame>
}`,...(F=(x=a.parameters)==null?void 0:x.docs)==null?void 0:F.source}}};var S,h,O;i.parameters={...i.parameters,docs:{...(S=i.parameters)==null?void 0:S.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`Brain Flow Empty State - \${STORYBOOK_NOTICE}\`}>\r
      <DecisionGraph kind="brain-flow" envelope={meshDialogueFixture} />\r
    </StorybookFrame>
}`,...(O=(h=i.parameters)==null?void 0:h.docs)==null?void 0:O.source}}};const _=["DecisionXRayGraph","ConflictMapGraph","CandidateLifecycleGraph","BrainFlowGraphEmpty"];export{i as BrainFlowGraphEmpty,a as CandidateLifecycleGraph,o as ConflictMapGraph,r as DecisionXRayGraph,_ as __namedExportsOrder,w as default};
