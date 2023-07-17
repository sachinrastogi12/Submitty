<?php

namespace app\entities\forum;

use DateTime;
use Doctrine\DBAL\Types\Types;
use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: "viewed_responses")]
class ThreadAccess {
    #[ORM\ManyToOne(targetEntity: Thread::class, inversedBy: "viewers")]
    #[ORM\JoinColumn(name: "thread_id", referencedColumnName: "id")]
    #[ORM\Id]
    protected Thread $thread;

    #[ORM\Id]
    #[ORM\Column(type: Types::STRING)]
    protected string $user_id;

    #[ORM\Column(type: Types::STRING)]
    protected DateTime $timestamp;
}
