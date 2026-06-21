import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { ControlCenterActionName, ControlCenterActionPayload } from "./controlCenterActions";
import { executeControlCenterAction } from "./controlCenterActions";

export function useControlCenterActionMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ action, payload }: { action: ControlCenterActionName; payload: ControlCenterActionPayload }) =>
      executeControlCenterAction(action, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["control-center"] });
    }
  });
}
