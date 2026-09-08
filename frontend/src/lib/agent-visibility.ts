import { z } from "zod";

const visibilityStateSchema = z.object({
  value: z.string().min(1),
  label: z.string().min(1),
  description: z.string(),
  export_marker: z.string(),
  scopes: z.array(z.string().min(1)),
});

export const agentVisibilityCatalogSchema = z
  .object({
    states: z.array(visibilityStateSchema).min(1),
    default: z.string().min(1),
  })
  .superRefine((catalog, context) => {
    const values = new Set<string>();
    for (const [index, state] of catalog.states.entries()) {
      if (values.has(state.value))
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["states", index, "value"],
          message: "Visibility state values must be unique",
        });
      values.add(state.value);
    }
    if (!values.has(catalog.default))
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["default"],
        message: "Default visibility must exist in states",
      });
  });

export type AgentVisibilityState = z.infer<typeof visibilityStateSchema>;
