import { Description, Field, Input, Label } from '@headlessui/react'
import clsx from 'clsx'

export default function TextBox() {
 return (
    <Field className="max-w-md">
      <Label className="text-sm font-medium text-black">Name</Label>
      <Description className="mt-1 text-sm text-black/60">
        Use your real name so people will recognize you.
      </Description>

      <Input
        type="text"
        placeholder=" "
        className={clsx(
          // layout & typography
          'mt-3 block w-full rounded-md px-3 py-2.5 text-sm text-black',

          // background: soft dark pill with a gentle top-to-bottom sheen
          'bg-[linear-gradient(180deg,rgba(255,255,255,0.07),rgba(255,255,255,0.04))]',

          // subtle structure
          'shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]',
          'ring-1 ring-inset ring-white/10',

          // placeholder + focus states
          'placeholder:text-black/30',
          'focus:outline-none focus:ring-2 focus:ring-white/25',

          // smooth transitions
          'transition-colors'
        )}
      />
    </Field>
  )
}