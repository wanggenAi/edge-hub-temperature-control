import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input
    className={cn(
      "flex h-10 w-full rounded-md border border-line bg-panel2 px-3 py-2 text-sm text-text outline-none placeholder:text-mute focus:border-neon/60",
      className
    )}
    ref={ref}
    {...props}
  />
));
Input.displayName = "Input";

export { Input };
