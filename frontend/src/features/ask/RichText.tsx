import { splitInline, toBlocks } from "@/lib/richText";

interface RichTextProps {
  text: string;
}

export function RichText({ text }: RichTextProps) {
  return (
    <div className="space-y-3">
      {toBlocks(text).map((block, blockIndex) => {
        const lines = block.split("\n");

        return (
          <div key={blockIndex} className="space-y-1">
            {lines.map((line, lineIndex) => {
              if (/^\d+\.\s/.test(line)) {
                return (
                  <p key={lineIndex} className="pl-4 text-sm text-muted-foreground">
                    {line}
                  </p>
                );
              }
              return (
                <p key={lineIndex} className="text-sm leading-relaxed">
                  {splitInline(line).map((part, partIndex) => {
                    if (part.type === "strong") {
                      return (
                        <strong key={partIndex} className="font-semibold text-foreground">
                          {part.value}
                        </strong>
                      );
                    }
                    if (part.type === "code") {
                      return (
                        <code
                          key={partIndex}
                          className="rounded bg-muted px-1 py-0.5 font-mono text-[13px]"
                        >
                          {part.value}
                        </code>
                      );
                    }
                    return <span key={partIndex}>{part.value}</span>;
                  })}
                </p>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}