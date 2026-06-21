import{j as r}from"./jsx-runtime-Cf8x2fCZ.js";import{E as n,M as l,S as t,P as i,L as d,N as p}from"./StaleState-D9R9Cw9u.js";import{S as b,a as c}from"./truthFixtures-BppgcTR0.js";import"./index-yBjzXJbu.js";import"./triangle-alert-BuFKT8-3.js";import"./index-BioFo8Zg.js";import"./wrench-C-UjqXZh.js";import"./circle-slash-Cl4tLSpW.js";const f={title:"Truth Components/State Components",parameters:{controls:{disable:!0}}},e={render:()=>r.jsx(b,{title:`Fallback States - ${c}`,children:r.jsxs("div",{className:"grid gap-4 lg:grid-cols-2",children:[r.jsx("div",{className:"rounded-lg border border-poly-line bg-poly-panel p-4",children:r.jsx(n,{errors:["Storybook fixture error; no backend request was made."]})}),r.jsx("div",{className:"rounded-lg border border-poly-line bg-poly-panel p-4",children:r.jsx(l,{warnings:["Storybook fixture source is absent."],source:null})}),r.jsx("div",{className:"rounded-lg border border-poly-line bg-poly-panel p-4",children:r.jsx(t,{warnings:["Storybook fixture represents last-known data."]})}),r.jsx("div",{className:"rounded-lg border border-poly-line bg-poly-panel p-4",children:r.jsx(i,{warnings:["Storybook fixture has partial source coverage."]})}),r.jsx("div",{className:"rounded-lg border border-poly-line bg-poly-panel p-4",children:r.jsx(d,{warnings:["Storybook fixture is locked; no permission is implied."]})}),r.jsx("div",{className:"rounded-lg border border-poly-line bg-poly-panel p-4",children:r.jsx(p,{warnings:["Storybook fixture surface is not implemented."]})})]})})};var o,a,s;e.parameters={...e.parameters,docs:{...(o=e.parameters)==null?void 0:o.docs,source:{originalSource:`{
  render: () => <StorybookFrame title={\`Fallback States - \${STORYBOOK_NOTICE}\`}>\r
      <div className="grid gap-4 lg:grid-cols-2">\r
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">\r
          <ErrorState errors={["Storybook fixture error; no backend request was made."]} />\r
        </div>\r
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">\r
          <MissingState warnings={["Storybook fixture source is absent."]} source={null} />\r
        </div>\r
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">\r
          <StaleState warnings={["Storybook fixture represents last-known data."]} />\r
        </div>\r
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">\r
          <PartialState warnings={["Storybook fixture has partial source coverage."]} />\r
        </div>\r
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">\r
          <LockedState warnings={["Storybook fixture is locked; no permission is implied."]} />\r
        </div>\r
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">\r
          <NotImplementedState warnings={["Storybook fixture surface is not implemented."]} />\r
        </div>\r
      </div>\r
    </StorybookFrame>
}`,...(s=(a=e.parameters)==null?void 0:a.docs)==null?void 0:s.source}}};const N=["AllSafeFallbackStates"];export{e as AllSafeFallbackStates,N as __namedExportsOrder,f as default};
