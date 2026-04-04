import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-neon/20 text-neon hover:bg-neon/30 border border-neon/40",
        accent: "bg-accent/20 text-accent hover:bg-accent/30 border border-accent/40",
        danger: "bg-danger/20 text-danger hover:bg-danger/30 border border-danger/40",
        ghost: "bg-transparent hover:bg-white/5 text-text border border-line"
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3",
        lg: "h-11 rounded-md px-8"
      }
    },
    defaultVariants: {
      variant: "default",
      size: "default"
    }
  }
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
});
Button.displayName = "Button";

export { Button, buttonVariants };
