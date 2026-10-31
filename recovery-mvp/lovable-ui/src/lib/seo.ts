export const pageHead = (title: string, description: string) => () => ({
  meta: [
    { title: `${title} · CENTERWAY` },
    { name: "description", content: description },
    { property: "og:title", content: `${title} · CENTERWAY` },
    { property: "og:description", content: description },
  ],
});

