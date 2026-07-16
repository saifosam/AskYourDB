// AskYourDB documentation site config
export default {
  base: "/AskYourDB/",
  title: "AskYourDB",
  description: "Natural Language → SQL → Database Results — powered by AI",

  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: "/AskYourDB/favicon.svg" }],
    [
      "style",
      {},
      `
      :root {
        --vp-c-brand-1: #6366f1;
        --vp-c-brand-2: #4f46e5;
        --vp-c-brand-3: #4338ca;
        --vp-c-brand-soft: rgba(99, 102, 241, 0.14);
        --vp-button-brand-bg: #6366f1;
        --vp-button-brand-hover-bg: #4f46e5;
        --vp-button-brand-active-bg: #4338ca;
        --vp-c-tip-bg: rgba(99, 102, 241, 0.1);
        --vp-c-tip-text: #6366f1;
        --vp-home-hero-name-color: transparent;
        --vp-home-hero-name-background: linear-gradient(135deg, #6366f1 0%, #818cf8 50%, #a5b4fc 100%);
      }
      .dark {
        --vp-c-brand-1: #818cf8;
        --vp-c-brand-2: #6366f1;
        --vp-c-brand-3: #4f46e5;
        --vp-c-brand-soft: rgba(129, 140, 248, 0.16);
      }
      `,
    ],
  ],

  themeConfig: {
    logo: "/AskYourDB/favicon.svg",

    nav: [
      { text: "Home", link: "/" },
      { text: "Guide", link: "/guide/getting-started" },
      { text: "Examples", link: "/examples" },
    ],

    sidebar: [
      {
        text: "Guide",
        items: [
          { text: "Getting Started", link: "/guide/getting-started" },
          { text: "Architecture", link: "/guide/architecture" },
          { text: "Design", link: "/guide/design" },
        ],
      },
    ],

    socialLinks: [
      { icon: "github", link: "https://github.com/saifosam/AskYourDB" },
    ],
  },
};
